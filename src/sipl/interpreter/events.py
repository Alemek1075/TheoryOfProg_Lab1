from __future__ import annotations

from dataclasses import asdict, dataclass

from .. import ast
from .errors import SiplRuntimeError

# Seq is not here: "S1; S2" only orders statements and gets no events of its own
_KINDS = {
    ast.Assign: "assign",
    ast.Skip: "skip",
    ast.If: "if",
    ast.While: "while",
    ast.Block: "block",
}


def _kind(stmt) -> str:
    return _KINDS[type(stmt)]


def _span(span) -> dict | None:
    return asdict(span) if span else None


@dataclass(frozen=True)
class Event:
    step: int  # number of the step during which the event happened, from 1


@dataclass(frozen=True)
class BeforeStatement(Event):
    statement: ast.Stmt

    def to_dict(self) -> dict:
        return {
            "event": "before_statement",
            "step": self.step,
            "statement": _kind(self.statement),
            "span": _span(self.statement.span),
        }


@dataclass(frozen=True)
class AfterStatement(Event):
    statement: ast.Stmt

    def to_dict(self) -> dict:
        return {
            "event": "after_statement",
            "step": self.step,
            "statement": _kind(self.statement),
            "span": _span(self.statement.span),
        }


@dataclass(frozen=True)
class VariableChanged(Event):
    """Sent for every assignment, also when the new value equals the old one."""

    statement: ast.Assign
    name: str
    old: int | None  # None if the variable had no value before
    new: int

    def to_dict(self) -> dict:
        return {
            "event": "variable_changed",
            "step": self.step,
            "name": self.name,
            "old": self.old,
            "new": self.new,
            "span": _span(self.statement.span),
        }


@dataclass(frozen=True)
class ConditionChecked(Event):
    statement: ast.If | ast.While
    result: bool

    def to_dict(self) -> dict:
        return {
            "event": "condition_checked",
            "step": self.step,
            "statement": _kind(self.statement),
            "result": self.result,
            "span": _span(self.statement.cond.span),
        }


@dataclass(frozen=True)
class Finished(Event):
    state: dict[str, int]

    def to_dict(self) -> dict:
        return {"event": "finished", "step": self.step, "state": dict(self.state)}


@dataclass(frozen=True)
class Failed(Event):
    error: SiplRuntimeError

    def to_dict(self) -> dict:
        return {
            "event": "failed",
            "step": self.step,
            "error": self.error.code,
            "message": self.error.message,
            "span": _span(self.error.span),
        }
