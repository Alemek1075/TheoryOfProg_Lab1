from __future__ import annotations

from dataclasses import dataclass, field
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


Expr = Union[Num, Var, BinOp]
Cond = Union[Compare, Or, Not]
Stmt = Union[Assign, Seq, If, While, Block, Skip]
