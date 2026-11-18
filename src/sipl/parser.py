from __future__ import annotations

from pathlib import Path

from lark import Lark, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedInput, UnexpectedToken
from lark.visitors import Transformer_NonRecursive

from . import ast
from .ast import SourceSpan

GRAMMAR_PATH = Path(__file__).parent / "grammar" / "sipl.lark"

# lexer="basic" keeps keywords reserved everywhere. The default contextual lexer
# reads "end" as a variable in places where the keyword "end" is not expected.
_lark = Lark(
    GRAMMAR_PATH.read_text(encoding="utf-8"),
    start="program",
    parser="lalr",
    lexer="basic",
    propagate_positions=True,
)

# the same grammar, but starting from an expression or a condition (debugger evaluate)
_lark_expression = Lark(
    GRAMMAR_PATH.read_text(encoding="utf-8"),
    start=["expr", "cond"],
    parser="lalr",
    lexer="basic",
    propagate_positions=True,
)

_TERMINALS = {t.name: t.pattern.value for t in _lark.terminals}
_NAMES = {"VAR": "variable", "NUMBER": "number", "$END": "end of program"}
_UNICODE_FORMS = {"–", "∨", "¬"}


class SiplSyntaxError(Exception):
    def __init__(self, message: str, span: SourceSpan):
        super().__init__(f"{span.line}:{span.column}: {message}")
        self.message = message
        self.span = span


def parse(text: str) -> ast.Program:
    try:
        tree = _lark.parse(text)
    except UnexpectedInput as e:
        raise _syntax_error(e, text) from None
    return _Builder().transform(tree)


def parse_expression(text: str) -> ast.Expr | ast.Cond:
    """Parse an expression like "X + 1" or a condition like "X > 1"."""
    for start in ("expr", "cond"):
        try:
            tree = _lark_expression.parse(text, start=start)
        except UnexpectedInput:
            continue
        return _Builder().transform(tree)
    raise SiplSyntaxError("not an expression or a condition", _end_span(text))


def _span(pos) -> SourceSpan:
    # works for both tree meta and tokens, they have the same fields
    return SourceSpan(
        pos.line, pos.column, pos.end_line, pos.end_column, pos.start_pos, pos.end_pos
    )


@v_args(meta=True)
class _Builder(Transformer_NonRecursive):
    def program(self, meta, c):
        return ast.Program(c[0], span=_span(meta))

    def seq(self, meta, c):
        return ast.Seq(c[0], c[1], span=_span(meta))

    def assign(self, meta, c):
        target = ast.Var(str(c[0]), span=_span(c[0]))
        return ast.Assign(target, c[1], span=_span(meta))

    def if_(self, meta, c):
        return ast.If(c[0], c[1], c[2], span=_span(meta))

    def while_(self, meta, c):
        return ast.While(c[0], c[1], span=_span(meta))

    def block(self, meta, c):
        return ast.Block(c[0], span=_span(meta))

    def skip(self, meta, c):
        return ast.Skip(span=_span(meta))

    def add(self, meta, c):
        return ast.BinOp("+", c[0], c[1], span=_span(meta))

    def sub(self, meta, c):
        return ast.BinOp("-", c[0], c[1], span=_span(meta))

    def mul(self, meta, c):
        return ast.BinOp("*", c[0], c[1], span=_span(meta))

    def num(self, meta, c):
        return ast.Num(int(c[0]), span=_span(meta))

    def neg_num(self, meta, c):
        return ast.Num(-int(c[0]), span=_span(meta))

    def var(self, meta, c):
        return ast.Var(str(c[0]), span=_span(meta))

    def or_(self, meta, c):
        return ast.Or(c[0], c[1], span=_span(meta))

    def not_(self, meta, c):
        return ast.Not(c[0], span=_span(meta))

    def eq(self, meta, c):
        return ast.Compare("=", c[0], c[1], span=_span(meta))

    def gt(self, meta, c):
        return ast.Compare(">", c[0], c[1], span=_span(meta))


def _syntax_error(e: UnexpectedInput, text: str) -> SiplSyntaxError:
    if isinstance(e, UnexpectedToken):
        expected = _describe(_expected(text))
        if e.token.type == "$END":
            message = f"unexpected end of program, expected {expected}"
            return SiplSyntaxError(message, _end_span(text))
        message = f"unexpected '{e.token}', expected {expected}"
        return SiplSyntaxError(message, _span(e.token))
    if isinstance(e, UnexpectedCharacters):
        pos = e.pos_in_stream or 0
        span = SourceSpan(e.line, e.column, e.line, e.column + 1, pos, pos + 1)
        return SiplSyntaxError(f"unexpected character '{e.char}'", span)
    return SiplSyntaxError("syntax error", _end_span(text))


def _expected(text: str) -> set[str]:
    # LALR does reductions before it notices the bad token, so the state saved in
    # the exception has already lost some valid continuations ('*' after a number).
    # Replay the text and ask what was accepted right before the bad token.
    parser = _lark.parse_interactive(text)
    accepts = parser.accepts()
    try:
        for _ in parser.iter_parse():
            accepts = parser.accepts()
        accepts = parser.accepts()
        parser.feed_eof()
    except UnexpectedInput:
        pass
    return accepts


def _describe(terminals) -> str:
    words = set()
    for name in terminals:
        if name in _NAMES:
            words.add(_NAMES[name])
        elif _TERMINALS[name] not in _UNICODE_FORMS:
            words.add(f"'{_TERMINALS[name]}'")
    return ", ".join(sorted(words))


def _end_span(text: str) -> SourceSpan:
    # Lark puts the end-of-input error on the last token, we want the place right after it
    stripped = text.rstrip()
    pos = len(stripped)
    line = stripped.count("\n") + 1
    column = pos - (stripped.rfind("\n") + 1) + 1
    return SourceSpan(line, column, line, column, pos, pos)
