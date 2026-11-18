import io
import subprocess
import sys

from sipl.dap.protocol import read_message, write_message
from sipl.dap.server import DebugServer, statement_lines
from sipl.parser import parse

POWER = """begin
  R := 1;
  while Y > 0 do
  begin
    R := R * X;
    Y := Y - 1
  end
end
"""


class Client:
    """Пише запити наперед і читає все, що відповів сервер."""

    def __init__(self):
        self.requests = io.BytesIO()
        self.seq = 0

    def send(self, command, **arguments):
        self.seq += 1
        message = {"seq": self.seq, "type": "request", "command": command}
        if arguments:
            message["arguments"] = arguments
        write_message(self.requests, message)
        return self

    def run(self):
        self.requests.seek(0)
        out = io.BytesIO()
        DebugServer(self.requests, out).serve()
        out.seek(0)
        messages = []
        while (message := read_message(out)) is not None:
            messages.append(message)
        return messages


def start(tmp_path, text=POWER, breakpoints=(), **launch):
    path = tmp_path / "prog.sipl"
    path.write_text(text, encoding="utf-8")
    client = Client().send("initialize", adapterID="sipl")
    client.send("launch", program=str(path), **launch)
    client.send(
        "setBreakpoints",
        source={"path": str(path)},
        breakpoints=[{"line": n} for n in breakpoints],
    )
    client.send("configurationDone")
    return client


def responses(messages, command):
    return [m for m in messages if m["type"] == "response" and m["command"] == command]


def events(messages, name):
    return [m["body"] if "body" in m else {} for m in messages if m.get("event") == name]


def stops(messages):
    return [e["reason"] for e in events(messages, "stopped")]


def test_statement_lines():
    assert statement_lines(parse(POWER)) == [2, 3, 5, 6]


def test_run_without_breakpoints(tmp_path):
    messages = start(tmp_path, state={"X": 2, "Y": 10}).run()
    assert responses(messages, "initialize")[0]["body"]["supportsConfigurationDoneRequest"]
    assert stops(messages) == []
    output = "".join(e["output"] for e in events(messages, "output"))
    assert "R = 1024" in output and "Y = 0" in output
    assert events(messages, "exited") == [{"exitCode": 0}]
    assert len(events(messages, "terminated")) == 1


def test_breakpoint_hits_every_iteration(tmp_path):
    client = start(tmp_path, breakpoints=[5], state={"X": 3, "Y": 2})
    client.send("stackTrace", threadId=1).send("variables", variablesReference=1)
    client.send("continue", threadId=1).send("variables", variablesReference=1)
    client.send("continue", threadId=1)
    messages = client.run()

    assert stops(messages) == ["breakpoint", "breakpoint"]
    frame = responses(messages, "stackTrace")[0]["body"]["stackFrames"][0]
    assert (frame["line"], frame["column"]) == (5, 5)
    assert frame["source"]["path"].endswith("prog.sipl")
    first, second = (r["body"]["variables"] for r in responses(messages, "variables"))
    assert first == [
        {"name": "R", "value": "1", "variablesReference": 0},
        {"name": "X", "value": "3", "variablesReference": 0},
        {"name": "Y", "value": "2", "variablesReference": 0},
    ]
    assert second[0] == {"name": "R", "value": "3", "variablesReference": 0}
    assert events(messages, "exited") == [{"exitCode": 0}]


def test_breakpoint_on_empty_line_moves_to_next_statement(tmp_path):
    client = start(tmp_path, breakpoints=[4, 100], state={"X": 1, "Y": 1})
    messages = client.send("disconnect").run()
    result = responses(messages, "setBreakpoints")[0]["body"]["breakpoints"]
    assert result[0] == {"verified": True, "line": 5}
    assert result[1]["verified"] is False


def test_stop_on_entry_and_step(tmp_path):
    client = start(tmp_path, stopOnEntry=True, state={"X": 2, "Y": 1})
    client.send("stackTrace", threadId=1)
    client.send("next", threadId=1).send("stackTrace", threadId=1)
    client.send("stepIn", threadId=1).send("stackTrace", threadId=1)
    messages = client.send("disconnect").run()
    assert stops(messages) == ["entry", "step", "step"]
    lines = [r["body"]["stackFrames"][0]["line"] for r in responses(messages, "stackTrace")]
    # R := 1, потім перевірка while, потім тіло циклу
    assert lines == [2, 3, 5]


def test_evaluate(tmp_path):
    client = start(tmp_path, breakpoints=[6], state={"X": 4, "Y": 2})
    for expression in ["R * X + 1", "Y > 1", "not (R = 4) or Y = 0", "Z + 1", "R :="]:
        client.send("evaluate", expression=expression, frameId=1, context="watch")
    messages = client.send("disconnect").run()
    results = responses(messages, "evaluate")
    assert [r["body"]["result"] for r in results[:3]] == ["17", "true", "false"]
    assert results[3]["success"] is False and "'Z' has no value" in results[3]["message"]
    assert results[4]["success"] is False


def test_runtime_error_stops_with_exception(tmp_path):
    text = "begin\n  A := 1;\n  B := C + A\nend\n"
    client = start(tmp_path, text=text).send("stackTrace", threadId=1)
    messages = client.send("continue", threadId=1).run()
    stopped = events(messages, "stopped")[0]
    assert stopped["reason"] == "exception"
    assert "'C' has no value" in stopped["text"]
    frame = responses(messages, "stackTrace")[0]["body"]["stackFrames"][0]
    assert (frame["line"], frame["column"]) == (3, 8)
    assert events(messages, "exited") == [{"exitCode": 3}]


def test_infinite_loop_stops_at_step_limit(tmp_path):
    text = "begin while 1 = 1 do skip end"
    messages = start(tmp_path, text=text, stepLimit=50).send("continue", threadId=1).run()
    assert stops(messages) == ["exception"]
    assert "step limit" in events(messages, "stopped")[0]["text"]


def test_launch_errors(tmp_path):
    bad = tmp_path / "bad.sipl"
    bad.write_text("begin X := end", encoding="utf-8")
    client = Client().send("initialize")
    client.send("launch")
    client.send("launch", program=str(tmp_path / "missing.sipl"))
    client.send("launch", program=str(bad))
    messages = client.send("configurationDone").run()
    launches = responses(messages, "launch")
    assert [r["success"] for r in launches] == [False, False, False]
    assert "1:12" in launches[2]["message"]
    assert len(events(messages, "terminated")) == 1


def test_bad_state(tmp_path):
    messages = start(tmp_path, state={"X": "2"}).run()
    assert responses(messages, "launch")[0]["success"] is False


def test_unknown_request_and_pause(tmp_path):
    messages = Client().send("initialize").send("fooBar").send("pause", threadId=1).run()
    assert responses(messages, "fooBar")[0]["success"] is False
    assert responses(messages, "pause")[0]["success"] is False
    assert responses(messages, "threads") == []


def test_threads_and_scopes():
    messages = Client().send("threads").send("scopes", frameId=1).run()
    assert responses(messages, "threads")[0]["body"]["threads"] == [{"id": 1, "name": "main"}]
    assert responses(messages, "scopes")[0]["body"]["scopes"][0]["variablesReference"] == 1


def test_runs_as_module(tmp_path):
    client = start(tmp_path, state={"X": 2, "Y": 3}).send("disconnect")
    result = subprocess.run(
        [sys.executable, "-m", "sipl.dap"],
        input=client.requests.getvalue(),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert b"R = 8" in result.stdout
