import json
import subprocess
import sys
from pathlib import Path

import pytest

from sipl.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"
POWER = str(EXAMPLES / "valid" / "power.sipl")
EQUALS = str(EXAMPLES / "invalid" / "equals.sipl")


@pytest.fixture
def cli(capsys):
    """Runs the CLI in this process, returns (exit code, stdout, stderr)."""

    def run(*args):
        code = main([str(arg) for arg in args])
        out, err = capsys.readouterr()
        return code, out, err

    return run


@pytest.fixture
def program(tmp_path):
    """Writes a program to a temporary file and returns its path."""

    def write(text, name="program.sipl"):
        path = tmp_path / name
        path.write_bytes(text.encode("utf-8"))
        return str(path)

    return write


def test_check_ok(cli):
    assert cli("check", POWER) == (0, "ok\n", "")


def test_check_ok_json(cli):
    code, out, err = cli("check", POWER, "--json")
    assert (code, json.loads(out), err) == (0, {"ok": True}, "")


def test_check_syntax_error(cli):
    code, out, err = cli("check", EQUALS)
    assert code == 1
    assert out == ""
    assert err.splitlines() == [
        f"{EQUALS}:2:5: error: unexpected '=', expected ':='",
        "    R = 1",
        "      ^",
    ]


def test_check_syntax_error_json(cli):
    code, out, err = cli("check", EQUALS, "--json")
    assert code == 1
    assert err == ""
    assert json.loads(out) == {
        "ok": False,
        "error": {
            "kind": "syntax_error",
            "message": "unexpected '=', expected ':='",
            "span": {"line": 2, "column": 5, "end_line": 2, "end_column": 6, "start": 10, "end": 11},
        },
    }


def test_every_invalid_example_fails_check(cli):
    for path in sorted((EXAMPLES / "invalid").glob("*.sipl")):
        code, out, err = cli("check", path)
        assert code == 1, path.name
        assert ": error: " in err


def test_parse_text(cli, program):
    code, out, err = cli("parse", program("begin R := X + 1 end"))
    assert code == 0
    assert out.splitlines() == [
        "Program",
        "  Assign",
        "    Var R",
        "    BinOp +",
        "      Var X",
        "      Num 1",
    ]


def test_parse_json(cli, program):
    code, out, err = cli("parse", program("begin skip end"), "--json")
    assert code == 0
    assert json.loads(out) == {
        "ok": True,
        "ast": {
            "type": "Program",
            "body": {
                "type": "Skip",
                "span": {"line": 1, "column": 7, "end_line": 1, "end_column": 11, "start": 6, "end": 10},
            },
            "span": {"line": 1, "column": 1, "end_line": 1, "end_column": 15, "start": 0, "end": 14},
        },
    }


def test_parse_json_has_all_node_types(cli, program):
    text = "begin if not X = 1 or X > 2 then begin X := X * 2; skip end else while X > 0 do X := 0 end"
    code, out, err = cli("parse", program(text), "--json")
    types = set()

    def walk(node):
        types.add(node["type"])
        for value in node.values():
            if isinstance(value, dict) and "type" in value:
                walk(value)

    walk(json.loads(out)["ast"])
    assert types == {
        "Program", "If", "Or", "Not", "Compare", "Block", "Seq",
        "Assign", "BinOp", "Skip", "While", "Var", "Num",
    }  # fmt: skip


def test_parse_too_deep(cli, program):
    text = "begin " + "; ".join("skip" for _ in range(5000)) + " end"
    code, out, err = cli("parse", program(text), "--json")
    assert code == 2
    assert json.loads(out)["error"]["kind"] == "too_deep"


def test_run_text(cli):
    assert cli("run", POWER, "X=2", "Y=10") == (0, "R = 1024\nX = 2\nY = 0\n", "")


def test_run_json(cli):
    code, out, err = cli("run", POWER, "X=2", "Y=3", "--json")
    assert code == 0
    assert json.loads(out) == {"ok": True, "state": {"R": 8, "X": 2, "Y": 0}, "steps": 11}


def test_run_options_before_state(cli):
    code, out, err = cli("run", "--json", "--step-limit", "100", POWER, "X=2", "Y=3")
    assert json.loads(out)["state"]["R"] == 8


def test_run_negative_input(cli, program):
    code, out, err = cli("run", program("begin R := X * X end"), "X=-12")
    assert (code, out) == (0, "R = 144\nX = -12\n")


def test_run_undefined_variable(cli):
    code, out, err = cli("run", POWER, "X=2")
    assert code == 3
    assert out == ""
    assert err.splitlines() == [
        f"{POWER}:3:9: error: variable 'Y' has no value",
        "    while Y > 0 do",
        "          ^",
    ]


def test_run_undefined_variable_json(cli):
    code, out, err = cli("run", POWER, "X=2", "--json")
    assert code == 3
    result = json.loads(out)
    assert result["ok"] is False
    assert result["error"]["kind"] == "undefined_variable"
    assert result["error"]["message"] == "variable 'Y' has no value"
    assert result["error"]["span"]["line"] == 3
    # what was done before the error is still reported
    assert result["state"] == {"R": 1, "X": 2}
    assert result["steps"] == 2


def test_run_step_limit(cli, program):
    path = program("begin while 1 = 1 do skip end")
    code, out, err = cli("run", path, "--step-limit", "50", "--json")
    assert code == 3
    result = json.loads(out)
    assert result["error"]["kind"] == "step_limit"
    assert result["error"]["message"] == "step limit of 50 exceeded"
    assert result["steps"] == 50


def test_run_syntax_error(cli):
    code, out, err = cli("run", EQUALS)
    assert code == 1


def test_run_big_number(cli, program):
    # 3 squared 14 times has about 7800 digits
    text = "begin R := 3; I := 0; while 14 > I do begin R := R * R; I := I + 1 end end"
    code, out, err = cli("run", program(text), "--json")
    assert code == 0
    assert json.loads(out)["state"]["R"] == 3 ** (2**14)


def test_trace_text(cli, program):
    path = program("begin\n  while X > 0 do\n    X := X - 1;\n  skip\nend")
    code, out, err = cli("trace", path, "X=1")
    assert code == 0
    assert out.splitlines() == [
        "    1  2:9     X > 0                    true",
        "    2  3:5     X := X - 1               X: 1 -> 0",
        "    3  2:9     X > 0                    false",
        "    4  4:3     skip",
        "finished in 4 steps",
        "X = 0",
    ]


def test_trace_json(cli, program):
    code, out, err = cli("trace", program("begin X := 1 end"), "--json")
    assert code == 0
    result = json.loads(out)
    assert result["ok"] is True
    assert [event["event"] for event in result["events"]] == [
        "before_statement",
        "variable_changed",
        "after_statement",
        "finished",
    ]
    assert result["events"][1] == {
        "event": "variable_changed",
        "step": 1,
        "name": "X",
        "old": None,
        "new": 1,
        "span": {"line": 1, "column": 7, "end_line": 1, "end_column": 13, "start": 6, "end": 12},
    }
    assert result["events"][-1] == {"event": "finished", "step": 1, "state": {"X": 1}}


def test_trace_runtime_error(cli, program):
    path = program("begin\n  X := 1;\n  R := Y\nend")
    code, out, err = cli("trace", path)
    assert code == 3
    assert out.splitlines() == ["    1  2:3     X := 1                   X: - -> 1"]
    assert err.splitlines()[0] == f"{path}:3:8: error: variable 'Y' has no value"


def test_trace_runtime_error_json(cli, program):
    code, out, err = cli("trace", program("begin X := 1; R := Y end"), "--json")
    assert code == 3
    result = json.loads(out)
    assert result["ok"] is False
    assert result["error"]["kind"] == "undefined_variable"
    assert result["events"][-1]["event"] == "failed"
    assert result["events"][-1]["error"] == "undefined_variable"


def test_missing_file(cli, tmp_path):
    path = str(tmp_path / "nothing.sipl")
    code, out, err = cli("run", path)
    assert code == 2
    assert err == f"{path}: error: cannot read file: No such file or directory\n"


def test_missing_file_json(cli, tmp_path):
    code, out, err = cli("check", tmp_path / "nothing.sipl", "--json")
    assert code == 2
    assert json.loads(out)["error"]["kind"] == "file_error"


def test_not_a_text_file(cli, tmp_path):
    path = tmp_path / "binary.sipl"
    path.write_bytes(b"\xff\xfe\x00begin")
    code, out, err = cli("check", path)
    assert code == 2
    assert "cannot read file: not a UTF-8 text" in err


def test_bom_and_windows_line_ends(cli, program):
    path = program("﻿begin\r\n  R := X + 1\r\nend\r\n")
    assert cli("run", path, "X=1") == (0, "R = 2\nX = 1\n", "")
    # the error still points at the right column of the right line
    path = program("﻿begin\r\n  R = 1\r\nend\r\n", "bad.sipl")
    code, out, err = cli("check", path)
    assert err.splitlines()[0] == f"{path}:2:5: error: unexpected '=', expected ':='"


def test_tabs_keep_the_mark_in_place(cli, program):
    code, out, err = cli("check", program("begin\n\tR = 1\nend"))
    assert err.splitlines()[1:] == ["  \tR = 1", "  \t  ^"]


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["run"],
        ["unknown", POWER],
        ["run", POWER, "X"],
        ["run", POWER, "X=abc"],
        ["run", POWER, "1X=2"],
        ["run", POWER, "--step-limit", "0"],
        ["run", POWER, "--step-limit", "many"],
        ["check", POWER, "X=1"],
    ],
)
def test_bad_command_line(args, capsys):
    with pytest.raises(SystemExit) as info:
        main(args)
    assert info.value.code == 2
    assert "usage: sipl" in capsys.readouterr().err


def run_process(*args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "sipl", *args],
        input=stdin,
        capture_output=True,
    )


def test_python_m_sipl():
    result = run_process("run", POWER, "X=2", "Y=3", "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"ok": True, "state": {"R": 8, "X": 2, "Y": 0}, "steps": 11}
    assert result.stderr == b""


def test_exit_codes_of_the_process():
    assert run_process("check", POWER).returncode == 0
    assert run_process("check", EQUALS).returncode == 1
    assert run_process("check", "nothing.sipl").returncode == 2
    assert run_process("run", POWER).returncode == 3


def test_stdin():
    result = run_process("run", "-", "X=5", stdin="begin R := X * 2 end".encode("utf-8"))
    assert result.returncode == 0
    assert result.stdout.split() == [b"R", b"=", b"10", b"X", b"=", b"5"]


def test_unicode_program_from_stdin():
    text = "begin while ¬ M = N do if M > N then M := M – N else N := N – M end"
    result = run_process("run", "-", "M=12", "N=18", "--json", stdin=text.encode("utf-8"))
    assert json.loads(result.stdout)["state"] == {"M": 6, "N": 6}
