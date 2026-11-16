from pathlib import Path

import pytest
from lark import Lark
from lark.exceptions import LarkError

ROOT = Path(__file__).parent.parent
GRAMMAR = ROOT / "src" / "sipl" / "grammar" / "sipl.lark"

parser = Lark(GRAMMAR.read_text(encoding="utf-8"), start="program", parser="lalr")

VALID = sorted((ROOT / "examples" / "valid").glob("*.sipl"))
INVALID = sorted((ROOT / "examples" / "invalid").glob("*.sipl"))


def test_enough_examples():
    assert len(VALID) >= 10
    assert len(INVALID) >= 10


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid(path):
    parser.parse(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid(path):
    with pytest.raises(LarkError):
        parser.parse(path.read_text(encoding="utf-8"))
