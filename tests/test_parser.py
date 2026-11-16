from pathlib import Path

import pytest

from sipl import ast
from sipl.ast import SourceSpan
from sipl.parser import SiplSyntaxError, parse

EXAMPLES = Path(__file__).parent.parent / "examples"
VALID = sorted((EXAMPLES / "valid").glob("*.sipl"))
INVALID = sorted((EXAMPLES / "invalid").glob("*.sipl"))


def body(text):
    return parse(f"begin {text} end").body


def error(text):
    with pytest.raises(SiplSyntaxError) as info:
        parse(text)
    return info.value


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_examples(path):
    assert isinstance(parse(path.read_text(encoding="utf-8")), ast.Program)


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_examples(path):
    error(path.read_text(encoding="utf-8"))


def test_assign():
    assert body("R := 1") == ast.Assign(ast.Var("R"), ast.Num(1))


def test_mul_before_add():
    expected = ast.BinOp("+", ast.Var("X"), ast.BinOp("*", ast.Var("Y"), ast.Var("Z")))
    assert body("R := X + Y * Z").value == expected


def test_sub_is_left_assoc():
    expected = ast.BinOp("-", ast.BinOp("-", ast.Var("X"), ast.Var("Y")), ast.Var("Z"))
    assert body("R := X - Y - Z").value == expected


def test_parens():
    expected = ast.BinOp("*", ast.BinOp("+", ast.Var("X"), ast.Var("Y")), ast.Var("Z"))
    assert body("R := (X + Y) * Z").value == expected
    assert body("R := (X)") == body("R := X")


def test_negative_number():
    assert body("R := -1").value == ast.Num(-1)
    assert body("R := X - -2").value == ast.BinOp("-", ast.Var("X"), ast.Num(-2))
    assert body("R := X-1").value == ast.BinOp("-", ast.Var("X"), ast.Num(1))


def test_not_before_or():
    cond = body("while not X = 1 or Y > 2 do skip").cond
    left = ast.Not(ast.Compare("=", ast.Var("X"), ast.Num(1)))
    right = ast.Compare(">", ast.Var("Y"), ast.Num(2))
    assert cond == ast.Or(left, right)


def test_while_body_is_one_statement():
    stmt = body("while X > 0 do X := X - 1; Y := 1")
    assert isinstance(stmt, ast.Seq)
    assert isinstance(stmt.first, ast.While)
    assert stmt.second == ast.Assign(ast.Var("Y"), ast.Num(1))


def test_else_branch_is_one_statement():
    stmt = body("if X > 0 then X := 1 else X := 2; Y := 3")
    assert isinstance(stmt, ast.Seq)
    assert isinstance(stmt.first, ast.If)


def test_block():
    stmt = body("while X > 0 do begin X := X - 1; Y := 1 end")
    assert isinstance(stmt, ast.While)
    assert isinstance(stmt.body, ast.Block)
    assert isinstance(stmt.body.body, ast.Seq)


def test_skip():
    assert body("skip") == ast.Skip()


def test_unicode_symbols():
    assert body("while ¬ M = N ∨ M > 1 do M := M – N") == body(
        "while not M = N or M > 1 do M := M - N"
    )


def test_keyword_prefix_is_variable():
    assert body("beginX := 1").target == ast.Var("beginX")
    assert body("order := 2").target == ast.Var("order")


def test_keyword_is_not_variable():
    error("begin R := then end")
    error("begin X := 1; end := 2 end")


def test_spans():
    program = parse("begin\n  R := 10\nend")
    assert program.span == SourceSpan(1, 1, 3, 4, 0, 19)
    assign = program.body
    assert assign.span == SourceSpan(2, 3, 2, 10, 8, 15)
    assert assign.target.span == SourceSpan(2, 3, 2, 4, 8, 9)
    assert assign.value.span == SourceSpan(2, 8, 2, 10, 13, 15)


def test_error_unexpected_token():
    e = error("begin\n  R = 1\nend")
    assert (e.span.line, e.span.column) == (2, 5)
    assert e.message == "unexpected '=', expected ':='"
    assert str(e) == "2:5: unexpected '=', expected ':='"


def test_error_extra_semicolon():
    e = error("begin\n  R := 1;\nend")
    assert (e.span.line, e.span.column) == (3, 1)
    assert e.message.startswith("unexpected 'end', expected ")
    assert "variable" in e.message


def test_error_end_of_program():
    e = error("begin\n  R := 1\n")
    assert (e.span.line, e.span.column) == (2, 9)
    assert e.message.startswith("unexpected end of program, expected ")
    assert "'end'" in e.message


def test_error_lists_all_expected():
    e = error("begin R := (X + 1 end")
    assert e.message == "unexpected 'end', expected ')', '*', '+', '-'"


def test_error_unknown_character():
    e = error("begin R := X / Y end")
    assert (e.span.line, e.span.column) == (1, 14)
    assert e.message == "unexpected character '/'"


def test_error_empty_text():
    e = error("")
    assert (e.span.line, e.span.column) == (1, 1)
    assert e.message == "unexpected end of program, expected 'begin'"
