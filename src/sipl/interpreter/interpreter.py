from __future__ import annotations

from .. import ast
from ..ast import SourceSpan

DEFAULT_STEP_LIMIT = 100_000


class SiplRuntimeError(Exception):
    def __init__(self, message: str, span: SourceSpan | None):
        where = f"{span.line}:{span.column}: " if span else ""
        super().__init__(where + message)
        self.message = message
        self.span = span


class UndefinedVariableError(SiplRuntimeError):
    pass


class StepLimitError(SiplRuntimeError):
    pass


class Interpreter:
    """Runs a program one step at a time.

    A step is one assignment, one skip or one condition check of if/while.
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
        # statements that are still to run, the next one is the last in the list
        self._todo: list[ast.Stmt] = [program.body]

    @property
    def done(self) -> bool:
        return not self._todo

    def run(self) -> dict[str, int]:
        while not self.done:
            self.step()
        return self.state

    def step(self) -> None:
        if self.done:
            return
        stmt = self._todo.pop()
        while isinstance(stmt, (ast.Seq, ast.Block)):
            if isinstance(stmt, ast.Seq):
                self._todo.append(stmt.second)
                stmt = stmt.first
            else:
                stmt = stmt.body

        if self.steps >= self.step_limit:
            self._todo.append(stmt)
            raise StepLimitError(f"step limit of {self.step_limit} exceeded", stmt.span)
        self.steps += 1

        try:
            self._execute(stmt)
        except RecursionError:
            raise SiplRuntimeError("expression is nested too deeply", stmt.span) from None

    def _execute(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.Assign):
            self.state[stmt.target.name] = self._eval(stmt.value)
        elif isinstance(stmt, ast.If):
            self._todo.append(stmt.then if self._test(stmt.cond) else stmt.orelse)
        elif isinstance(stmt, ast.While):
            if self._test(stmt.cond):
                # after the body the loop goes back to checking its condition
                self._todo.append(stmt)
                self._todo.append(stmt.body)
        # skip does nothing

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
