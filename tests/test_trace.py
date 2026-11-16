import json
from pathlib import Path

import pytest

from sipl import ast
from sipl.interpreter import (
    AfterStatement,
    BeforeStatement,
    ConditionChecked,
    Failed,
    Finished,
    Interpreter,
    StepLimitError,
    UndefinedVariableError,
    VariableChanged,
    trace,
)
from sipl.parser import parse

VALID = Path(__file__).parent.parent / "examples" / "valid"

# enough input for every file in examples/valid
INPUT = {"X": 7, "Y": 3, "Z": 2, "M": 12, "N": 18}


def trace_text(text, state=None, **kwargs):
    return trace(parse(text), state, **kwargs)


def short(events):
    """Events as short strings, easier to compare than the full dicts."""
    out = []
    for e in events:
        d = e.to_dict()
        if isinstance(e, (BeforeStatement, AfterStatement)):
            word = "before" if isinstance(e, BeforeStatement) else "after"
            out.append(f"{d['step']} {word} {d['statement']}")
        elif isinstance(e, VariableChanged):
            out.append(f"{d['step']} {d['name']}: {d['old']} -> {d['new']}")
        elif isinstance(e, ConditionChecked):
            out.append(f"{d['step']} check {d['statement']} = {d['result']}")
        elif isinstance(e, Finished):
            out.append(f"{d['step']} finished")
        else:
            out.append(f"{d['step']} failed {d['error']}")
    return out


def test_assign():
    assert short(trace_text("begin X := 1 end")) == [
        "1 before assign",
        "1 X: None -> 1",
        "1 after assign",
        "1 finished",
    ]


def test_old_value():
    events = trace_text("begin X := X + 1 end", {"X": 5})
    assert short(events)[1] == "1 X: 5 -> 6"


def test_skip():
    assert short(trace_text("begin skip end")) == [
        "1 before skip",
        "1 after skip",
        "1 finished",
    ]


def test_if():
    text = "begin if X > 0 then R := 1 else R := 2 end"
    assert short(trace_text(text, {"X": 5})) == [
        "1 before if",
        "1 check if = True",
        "2 before assign",
        "2 R: None -> 1",
        "2 after assign",
        "2 after if",
        "2 finished",
    ]
    assert short(trace_text(text, {"X": 0}))[1:4] == [
        "1 check if = False",
        "2 before assign",
        "2 R: None -> 2",
    ]


def test_while():
    text = "begin while X > 0 do X := X - 1 end"
    assert short(trace_text(text, {"X": 2})) == [
        "1 before while",
        "1 check while = True",
        "2 before assign",
        "2 X: 2 -> 1",
        "2 after assign",
        "3 check while = True",
        "4 before assign",
        "4 X: 1 -> 0",
        "4 after assign",
        "5 check while = False",
        "5 after while",
        "5 finished",
    ]


def test_while_with_zero_iterations():
    assert short(trace_text("begin while X > 0 do skip end", {"X": 0})) == [
        "1 before while",
        "1 check while = False",
        "1 after while",
        "1 finished",
    ]


def test_block():
    assert short(trace_text("begin begin X := 1; Y := 2 end; skip end")) == [
        "1 before block",
        "1 before assign",
        "1 X: None -> 1",
        "1 after assign",
        "2 before assign",
        "2 Y: None -> 2",
        "2 after assign",
        "2 after block",
        "3 before skip",
        "3 after skip",
        "3 finished",
    ]


def test_finished_has_final_state():
    last = trace_text("begin R := X * 2 end", {"X": 4})[-1]
    assert isinstance(last, Finished)
    assert last.state == {"X": 4, "R": 8}
    assert last.to_dict() == {"event": "finished", "step": 1, "state": {"X": 4, "R": 8}}


def test_undefined_variable():
    events = trace_text("begin\n  X := 1;\n  R := Y\nend")
    assert short(events) == [
        "1 before assign",
        "1 X: None -> 1",
        "1 after assign",
        "2 before assign",
        "2 failed undefined_variable",
    ]
    assert events[-1].to_dict() == {
        "event": "failed",
        "step": 2,
        "error": "undefined_variable",
        "message": "variable 'Y' has no value",
        "span": {"line": 3, "column": 8, "end_line": 3, "end_column": 9, "start": 23, "end": 24},
    }


def test_step_limit():
    events = trace_text("begin while 1 = 1 do skip end", step_limit=4)
    assert short(events)[-3:] == ["4 before skip", "4 after skip", "5 failed step_limit"]
    assert events[-1].error.message == "step limit of 4 exceeded"


def test_events_keep_the_nodes():
    program = parse("begin\n  X := 1\nend")
    before = trace(program)[0]
    assert before.statement is program.body
    assert before.to_dict() == {
        "event": "before_statement",
        "step": 1,
        "statement": "assign",
        "span": {"line": 2, "column": 3, "end_line": 2, "end_column": 9, "start": 8, "end": 14},
    }


def test_condition_span_is_the_condition():
    event = trace_text("begin if X > 0 then skip else skip end", {"X": 1})[1]
    assert isinstance(event, ConditionChecked)
    span = event.to_dict()["span"]
    assert (span["start"], span["end"]) == (9, 14)


def test_listeners_get_events_while_running():
    interpreter = Interpreter(parse("begin X := 1; Y := 2 end"))
    first, second = [], []
    interpreter.subscribe(first.append)
    interpreter.subscribe(second.append)
    interpreter.step()
    assert short(first) == ["1 before assign", "1 X: None -> 1", "1 after assign"]
    interpreter.step()
    assert len(first) == 7
    assert first == second


def test_listener_gets_failed_before_the_exception():
    interpreter = Interpreter(parse("begin R := X end"))
    events = []
    interpreter.subscribe(events.append)
    with pytest.raises(UndefinedVariableError) as info:
        interpreter.run()
    assert isinstance(events[-1], Failed)
    assert events[-1].error is info.value
    assert interpreter.error is info.value
    assert interpreter.done


def test_run_can_go_on_after_raising_the_limit():
    interpreter = Interpreter(parse("begin X := 1; Y := 2; Z := 3 end"), step_limit=2)
    with pytest.raises(StepLimitError):
        interpreter.run()
    assert interpreter.state == {"X": 1, "Y": 2}
    interpreter.step_limit = 10
    assert interpreter.run() == {"X": 1, "Y": 2, "Z": 3}


def test_next_statement():
    program = parse("begin X := 2; while X > 0 do begin X := X - 1 end end")
    interpreter = Interpreter(program)
    assert isinstance(interpreter.next_statement, ast.Assign)
    interpreter.step()
    assert isinstance(interpreter.next_statement, ast.While)
    interpreter.step()
    assert interpreter.next_statement == parse("begin X := X - 1 end").body
    interpreter.step()
    assert isinstance(interpreter.next_statement, ast.While)
    interpreter.run()
    assert interpreter.next_statement is None


@pytest.mark.parametrize("path", sorted(VALID.glob("*.sipl")), ids=lambda p: p.stem)
def test_examples(path):
    events = trace(parse(path.read_text(encoding="utf-8")), INPUT)
    assert isinstance(events[-1], Finished)

    # the whole trace goes to JSON and back
    dicts = [e.to_dict() for e in events]
    assert json.loads(json.dumps(dicts)) == dicts

    # steps only grow
    steps = [e.step for e in events]
    assert steps == sorted(steps)

    # every statement that starts also ends, in the right order
    open_statements = []
    for e in events:
        if isinstance(e, BeforeStatement):
            open_statements.append(e.statement)
        elif isinstance(e, AfterStatement):
            assert open_statements.pop() is e.statement
    assert open_statements == []
