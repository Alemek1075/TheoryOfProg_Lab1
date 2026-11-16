from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Union


@dataclass(frozen=True)
class SourceSpan:
    """Position of a node in the source text. Lines and columns start from 1."""

    line: int
    column: int
    end_line: int
    end_column: int
    start: int
    end: int


@dataclass(frozen=True)
class Node:
    # span is not compared, so two trees are equal when their structure is equal.
    # The parser always sets it, None is only for nodes built by hand.
    span: SourceSpan | None = field(default=None, kw_only=True, compare=False, repr=False)


@dataclass(frozen=True)
class Num(Node):
    value: int


@dataclass(frozen=True)
class Var(Node):
    name: str


@dataclass(frozen=True)
class BinOp(Node):
    op: str  # "+", "-", "*"
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Compare(Node):
    op: str  # "=", ">"
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Or(Node):
    left: Cond
    right: Cond


@dataclass(frozen=True)
class Not(Node):
    cond: Cond


@dataclass(frozen=True)
class Assign(Node):
    target: Var
    value: Expr


@dataclass(frozen=True)
class Seq(Node):
    first: Stmt
    second: Stmt


@dataclass(frozen=True)
class If(Node):
    cond: Cond
    then: Stmt
    orelse: Stmt


@dataclass(frozen=True)
class While(Node):
    cond: Cond
    body: Stmt


@dataclass(frozen=True)
class Block(Node):
    body: Stmt


@dataclass(frozen=True)
class Skip(Node):
    pass


@dataclass(frozen=True)
class Program(Node):
    body: Stmt


def fields_of(node: Node):
    """Pairs (name, value) for all fields of a node except span."""
    return [(f.name, getattr(node, f.name)) for f in fields(node) if f.name != "span"]


def to_dict(node: Node) -> dict:
    """The tree as plain dicts, ready for JSON."""
    out: dict = {"type": type(node).__name__}
    for name, value in fields_of(node):
        out[name] = to_dict(value) if isinstance(value, Node) else value
    out["span"] = asdict(node.span) if node.span else None
    return out


Expr = Union[Num, Var, BinOp]
Cond = Union[Compare, Or, Not]
Stmt = Union[Assign, Seq, If, While, Block, Skip]
