from __future__ import annotations

from ..ast import SourceSpan


class SiplRuntimeError(Exception):
    code = "runtime_error"

    def __init__(self, message: str, span: SourceSpan | None):
        where = f"{span.line}:{span.column}: " if span else ""
        super().__init__(where + message)
        self.message = message
        self.span = span


class UndefinedVariableError(SiplRuntimeError):
    code = "undefined_variable"


class StepLimitError(SiplRuntimeError):
    code = "step_limit"
