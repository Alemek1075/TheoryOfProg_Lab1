from pathlib import Path

import pytest

from sipl.interpreter import (
    Interpreter,
    SiplRuntimeError,
    StepLimitError,
    UndefinedVariableError,
    run,
)
from sipl.parser import parse

VALID = Path(__file__).parent.parent / "examples" / "valid"

# file, input state, expected values in the final state
EXAMPLES = [
    ("power", {"X": 2, "Y": 3}, {"R": 8}),
    ("power", {"X": 5, "Y": 0}, {"R": 1}),
    ("gcd", {"M": 12, "N": 18}, {"R": 6}),
    ("gcd_unicode", {"M": 8, "N": 16}, {"M": 8, "N": 8}),
    ("factorial", {"N": 5}, {"R": 120}),
    ("factorial", {"N": 0}, {"R": 1}),
    ("sum", {"N": 10}, {"R": 55}),
    ("fib", {"N": 10}, {"R": 55}),
    ("div", {"X": 17, "Y": 5}, {"R": 3, "X": 2}),
    ("max", {"X": 3, "Y": 7}, {"R": 7}),
    ("max", {"X": 7, "Y": 3}, {"R": 7}),
    ("abs", {"X": -5}, {"R": 5}),
    ("abs", {"X": 5}, {"R": 5}),
    ("skip", {"X": 1}, {"X": 1}),
    ("blocks", {}, {"X": 1, "Y": 2, "R": 3}),
    ("cond", {"X": 0, "Y": 0}, {"R": 0}),
    ("cond", {"X": 0, "Y": -1}, {"R": 1}),
    ("expr", {"X": 1, "Y": 2, "Z": 3}, {"R": 3}),
]


def run_text(text, state=None, **kwargs):
    return run(parse(text), state, **kwargs)


@pytest.mark.parametrize("name, state, expected", EXAMPLES)
def test_examples(name, state, expected):
    program = parse((VALID / f"{name}.sipl").read_text(encoding="utf-8"))
    result = run(program, state)
    assert {var: result[var] for var in expected} == expected


def test_every_valid_example_is_checked():
    files = {path.stem for path in VALID.glob("*.sipl")}
    assert files == {name for name, _, _ in EXAMPLES}


def test_assign_and_arithmetic():
    assert run_text("begin R := 2 + 3 * 4 - 1 end") == {"R": 13}
    assert run_text("begin R := (2 + 3) * 4 end") == {"R": 20}
    assert run_text("begin R := 1 - 2 - 3 end") == {"R": -4}
    assert run_text("begin R := -2 * -3 end") == {"R": 6}


def test_big_numbers():
    assert run_text("begin R := X * X * X end", {"X": 10**20}) == {"X": 10**20, "R": 10**60}


def test_input_state_is_not_changed():
    state = {"X": 1}
    result = run_text("begin X := X + 1 end", state)
    assert state == {"X": 1}
    assert result == {"X": 2}


def test_if():
    text = "begin if X > 0 then R := 1 else R := 2 end"
    assert run_text(text, {"X": 5})["R"] == 1
    assert run_text(text, {"X": 0})["R"] == 2


def test_conditions():
    text = "begin if {} then R := 1 else R := 0 end"
    state = {"X": 1, "Y": 2}
    assert run_text(text.format("X = 1"), state)["R"] == 1
    assert run_text(text.format("X = Y"), state)["R"] == 0
    assert run_text(text.format("Y > X"), state)["R"] == 1
    assert run_text(text.format("X > X"), state)["R"] == 0
    assert run_text(text.format("not X = Y"), state)["R"] == 1
    assert run_text(text.format("X = 5 or Y = 2"), state)["R"] == 1
    assert run_text(text.format("X = 5 or Y = 5"), state)["R"] == 0
    assert run_text(text.format("not (X = 5 or Y = 5)"), state)["R"] == 1


def test_while_with_zero_iterations():
    assert run_text("begin while X > 0 do X := X - 1 end", {"X": 0}) == {"X": 0}


def test_statement_after_loop():
    result = run_text("begin while X > 0 do X := X - 1; R := 7 end", {"X": 3})
    assert result == {"X": 0, "R": 7}


def test_nested_loops():
    text = """
    begin
      R := 0;
      I := 0;
      while N > I do
      begin
        J := 0;
        while N > J do
        begin
          R := R + 1;
          J := J + 1
        end;
        I := I + 1
      end
    end
    """
    assert run_text(text, {"N": 4})["R"] == 16


def test_undefined_variable():
    with pytest.raises(UndefinedVariableError) as info:
        run_text("begin\n  R := X + 1\nend")
    e = info.value
    assert e.message == "variable 'X' has no value"
    assert (e.span.line, e.span.column) == (2, 8)
    assert str(e) == "2:8: variable 'X' has no value"


def test_undefined_variable_in_condition():
    with pytest.raises(UndefinedVariableError):
        run_text("begin while X > 0 do skip end")


def test_or_checks_both_sides():
    # X = 1 is already true, but Y still has to be defined
    with pytest.raises(UndefinedVariableError):
        run_text("begin if X = 1 or Y = 1 then skip else skip end", {"X": 1})


def test_step_limit():
    with pytest.raises(StepLimitError) as info:
        run_text("begin\n  while 1 = 1 do\n    skip\nend", step_limit=100)
    e = info.value
    assert e.message == "step limit of 100 exceeded"
    assert e.span.line in (2, 3)


def test_step_limit_is_exact():
    # 3 assignments are 3 steps
    text = "begin X := 1; Y := 2; Z := 3 end"
    assert run_text(text, step_limit=3) == {"X": 1, "Y": 2, "Z": 3}
    with pytest.raises(StepLimitError):
        run_text(text, step_limit=2)


def test_default_step_limit_stops_endless_loop():
    with pytest.raises(StepLimitError):
        run_text("begin X := 0; while X > -1 do X := X + 1 end")


def test_step_by_step():
    interpreter = Interpreter(parse("begin X := 1; if X > 0 then R := X else skip end"))
    assert not interpreter.done
    interpreter.step()
    assert interpreter.state == {"X": 1}
    interpreter.step()  # condition check
    assert interpreter.state == {"X": 1}
    interpreter.step()
    assert interpreter.state == {"X": 1, "R": 1}
    assert interpreter.done
    assert interpreter.steps == 3
    interpreter.step()  # nothing left, does nothing
    assert interpreter.steps == 3


def test_steps_are_counted():
    # 1 assignment + 3 loop bodies + 4 condition checks
    interpreter = Interpreter(parse("begin X := 3; while X > 0 do X := X - 1 end"))
    interpreter.run()
    assert interpreter.steps == 8


def test_long_program():
    text = "begin R := 0; " + "; ".join("R := R + 1" for _ in range(5000)) + " end"
    assert run_text(text) == {"R": 5000}


def test_too_deep_expression():
    text = "begin R := " + " + ".join(["1"] * 20000) + " end"
    with pytest.raises(SiplRuntimeError) as info:
        run_text(text)
    assert info.value.message == "expression is nested too deeply"
