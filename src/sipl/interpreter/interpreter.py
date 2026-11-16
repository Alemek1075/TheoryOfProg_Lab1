from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .. import ast
from .errors import SiplRuntimeError, StepLimitError, UndefinedVariableError
from .events import (
    AfterStatement,
    BeforeStatement,
    ConditionChecked,
    Event,
    Failed,
    Finished,
    VariableChanged,
)

DEFAULT_STEP_LIMIT = 100_000


@dataclass
class _After:
    """Marker in the todo list: the statement ends when we get here."""

    stmt: ast.Stmt


@dataclass
class _Recheck:
    """Marker in the todo list: the loop body is done, check the condition again."""

    stmt: ast.While


class Interpreter:
    """Runs a program one step at a time.

    A step is one assignment, one skip or one condition check of if/while.
    Everything that happens is reported to the listeners as events.
    """

    def __init__(
        self,
        program: ast.Program,
        state: dict[str, int] | None = None,
        step_limit: int = DEFAULT_STEP_LIMIT,
    ):
        self.state = dict(state or {})
        self.step_limit = step_limit
        self.steps = 0
        self.error: SiplRuntimeError | None = None
        # what is still to run, the next item is the last in the list
        self._todo: list = [program.body]
        self._listeners: list[Callable[[Event], None]] = []

    def subscribe(self, listener: Callable[[Event], None]) -> None:
        self._listeners.append(listener)

    @property
    def done(self) -> bool:
        return not self._todo

    @property
    def next_statement(self) -> ast.Stmt | None:
        """The statement that the next step will run, None when nothing is left."""
        if self.done:
            return None
        item = self._todo[-1]
        if isinstance(item, _Recheck):
            return item.stmt
        while isinstance(item, (ast.Seq, ast.Block)):
            item = item.first if isinstance(item, ast.Seq) else item.body
        return item

    def run(self) -> dict[str, int]:
        while not self.done:
            self.step()
        return self.state

    def step(self) -> None:
        if self.done:
            return
        if self.steps >= self.step_limit:
            # nothing is removed from the todo list here, so the run can go on
            # if the caller raises step_limit
            message = f"step limit of {self.step_limit} exceeded"
            error = StepLimitError(message, self.next_statement.span)
            self._emit(Failed(self.steps + 1, error))
            raise error

        self.steps += 1
        current = self.next_statement
        try:
            self._run_next()
        except RecursionError:
            self._fail(SiplRuntimeError("expression is nested too deeply", current.span))
        except SiplRuntimeError as error:
            self._fail(error)

        # statements that end together with this step
        while self._todo and isinstance(self._todo[-1], _After):
            self._emit(AfterStatement(self.steps, self._todo.pop().stmt))
        if self.done:
            self._emit(Finished(self.steps, dict(self.state)))

    def _fail(self, error: SiplRuntimeError) -> None:
        self.error = error
        self._todo.clear()
        self._emit(Failed(self.steps, error))
        raise error from None

    def _emit(self, event: Event) -> None:
        for listener in self._listeners:
            listener(event)

    def _run_next(self) -> None:
        item = self._todo.pop()
        while isinstance(item, (ast.Seq, ast.Block)):
            if isinstance(item, ast.Seq):
                self._todo.append(item.second)
                item = item.first
            else:
                self._emit(BeforeStatement(self.steps, item))
                self._todo.append(_After(item))
                item = item.body

        if isinstance(item, _Recheck):
            self._check_loop(item.stmt)
        elif isinstance(item, ast.While):
            self._emit(BeforeStatement(self.steps, item))
            self._check_loop(item)
        elif isinstance(item, ast.If):
            self._emit(BeforeStatement(self.steps, item))
            branch = item.then if self._check(item) else item.orelse
            self._todo.append(_After(item))
            self._todo.append(branch)
        elif isinstance(item, ast.Assign):
            self._emit(BeforeStatement(self.steps, item))
            name = item.target.name
            old = self.state.get(name)
            new = self._eval(item.value)
            self.state[name] = new
            self._emit(VariableChanged(self.steps, item, name, old, new))
            self._emit(AfterStatement(self.steps, item))
        else:  # skip
            self._emit(BeforeStatement(self.steps, item))
            self._emit(AfterStatement(self.steps, item))

    def _check_loop(self, stmt: ast.While) -> None:
        if self._check(stmt):
            self._todo.append(_Recheck(stmt))
            self._todo.append(stmt.body)
        else:
            self._emit(AfterStatement(self.steps, stmt))

    def _check(self, stmt: ast.If | ast.While) -> bool:
        result = self._test(stmt.cond)
        self._emit(ConditionChecked(self.steps, stmt, result))
        return result

    def _eval(self, expr: ast.Expr) -> int:
        if isinstance(expr, ast.Num):
            return expr.value
        if isinstance(expr, ast.Var):
            if expr.name not in self.state:
                raise UndefinedVariableError(f"variable '{expr.name}' has no value", expr.span)
            return self.state[expr.name]
        left = self._eval(expr.left)
        right = self._eval(expr.right)
        if expr.op == "+":
            return left + right
        if expr.op == "-":
            return left - right
        return left * right

    def _test(self, cond: ast.Cond) -> bool:
        if isinstance(cond, ast.Not):
            return not self._test(cond.cond)
        if isinstance(cond, ast.Or):
            # No short-circuit. In the course semantics b1 ∨ b2 is S2(or, b1, b2),
            # so both sides are evaluated and an undefined one makes the whole undefined.
            left = self._test(cond.left)
            right = self._test(cond.right)
            return left or right
        left = self._eval(cond.left)
        right = self._eval(cond.right)
        return left == right if cond.op == "=" else left > right


def run(
    program: ast.Program,
    state: dict[str, int] | None = None,
    step_limit: int = DEFAULT_STEP_LIMIT,
) -> dict[str, int]:
    """Run the program on the given state and return the final state."""
    return Interpreter(program, state, step_limit).run()


def trace(
    program: ast.Program,
    state: dict[str, int] | None = None,
    step_limit: int = DEFAULT_STEP_LIMIT,
) -> list[Event]:
    """Run the program and return all its events.

    The last event is Finished, or Failed if the run stopped with an error.
    """
    events: list[Event] = []
    interpreter = Interpreter(program, state, step_limit)
    interpreter.subscribe(events.append)
    try:
        interpreter.run()
    except SiplRuntimeError:
        pass
    return events
