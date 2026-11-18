"""Debug adapter для SIPL.

Працює через stdin/stdout, VS Code запускає його як `python -m sipl.dap`.
Потік у SIPL один, кадр стеку теж один, бо процедур у мові немає.

Програма виконується в тому ж потоці, що читає запити: continue або next
крутить Interpreter.step(), поки не дійде до точки зупину, кінця або помилки.
Через це pause не підтримується, але нескінченний цикл все одно зупиниться
на step limit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO

from .. import ast
from ..interpreter import DEFAULT_STEP_LIMIT, Interpreter, SiplRuntimeError
from ..parser import SiplSyntaxError, parse, parse_expression
from .protocol import read_message, write_message

THREAD_ID = 1
FRAME_ID = 1
VARIABLES_REF = 1


def statement_lines(program: ast.Program) -> list[int]:
    """Рядки, з яких починаються оператори, на яких дебагер може зупинитись."""
    lines = set()
    todo: list[ast.Stmt] = [program.body]
    while todo:
        node = todo.pop()
        if isinstance(node, ast.Seq):
            todo += [node.first, node.second]
        elif isinstance(node, ast.Block):
            todo.append(node.body)
        else:
            if node.span is not None:
                lines.add(node.span.line)
            if isinstance(node, ast.If):
                todo += [node.then, node.orelse]
            elif isinstance(node, ast.While):
                todo.append(node.body)
    return sorted(lines)


def _format(value: int | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class DebugServer:
    def __init__(self, reader: BinaryIO, writer: BinaryIO):
        self.reader = reader
        self.writer = writer
        self.seq = 0
        self.running = True

        self.path: str | None = None
        self.program: ast.Program | None = None
        self.interpreter: Interpreter | None = None
        self.stop_on_entry = False
        self.breakpoints: set[int] = set()
        # місце, де зупинились, для stackTrace
        self.stopped_at: ast.SourceSpan | None = None
        self.error: SiplRuntimeError | None = None
        self.terminated = False

    # --- транспорт ---

    def serve(self) -> None:
        while self.running:
            message = read_message(self.reader)
            if message is None:
                break
            if message.get("type") == "request":
                self._handle(message)

    def _send(self, message: dict[str, Any]) -> None:
        self.seq += 1
        message["seq"] = self.seq
        write_message(self.writer, message)

    def _event(self, event: str, body: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"type": "event", "event": event}
        if body is not None:
            message["body"] = body
        self._send(message)

    def _respond(self, request, body=None, error: str | None = None) -> None:
        message: dict[str, Any] = {
            "type": "response",
            "request_seq": request["seq"],
            "command": request["command"],
            "success": error is None,
        }
        if error is not None:
            message["message"] = error
        if body is not None:
            message["body"] = body
        self._send(message)

    def _output(self, text: str, category: str = "console") -> None:
        self._event("output", {"category": category, "output": text})

    def _handle(self, request: dict[str, Any]) -> None:
        command = request.get("command", "")
        handler = getattr(self, "_on_" + command, None)
        if handler is None:
            self._respond(request, error=f"unsupported request '{command}'")
            return
        args = request.get("arguments") or {}
        try:
            handler(request, args)
        except Exception as error:  # adapter must answer even when something breaks
            self._respond(request, error=f"internal error: {error}")

    # --- запити ---

    def _on_initialize(self, request, args):
        self._respond(
            request,
            {
                "supportsConfigurationDoneRequest": True,
                "supportsEvaluateForHovers": True,
                "supportsTerminateRequest": True,
            },
        )

    def _on_launch(self, request, args):
        path = args.get("program")
        if not path:
            self._respond(request, error="launch.json has no 'program'")
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as e:
            self._respond(request, error=f"cannot read {path}: {e}")
            return
        try:
            self.program = parse(text)
        except SiplSyntaxError as e:
            self._output(f"{path}:{e}\n", "stderr")
            self._respond(request, error=f"syntax error at {e}")
            return

        state = args.get("state") or {}
        bad = [k for k, v in state.items() if not isinstance(v, int) or isinstance(v, bool)]
        if bad:
            self._respond(request, error=f"state values must be integers: {', '.join(bad)}")
            return
        limit = args.get("stepLimit", DEFAULT_STEP_LIMIT)
        self.path = str(Path(path).resolve())
        self.interpreter = Interpreter(self.program, state, limit)
        self.stop_on_entry = bool(args.get("stopOnEntry", False))
        self._respond(request)
        # VS Code sends breakpoints after this event. It goes here and not after
        # initialize, so the program is already parsed when the breakpoints come.
        self._event("initialized")

    def _on_setBreakpoints(self, request, args):
        lines = statement_lines(self.program) if self.program else []
        wanted = [b["line"] for b in args.get("breakpoints", [])]
        self.breakpoints = set()
        result = []
        for line in wanted:
            # точка зупину на рядку без оператора переїжджає на наступний оператор
            target = next((n for n in lines if n >= line), None)
            if target is None:
                result.append({"verified": False, "line": line, "message": "no statement here"})
            else:
                self.breakpoints.add(target)
                result.append({"verified": True, "line": target})
        self._respond(request, {"breakpoints": result})

    def _on_setExceptionBreakpoints(self, request, args):
        self._respond(request, {"breakpoints": []})

    def _on_configurationDone(self, request, args):
        self._respond(request)
        if self.interpreter is None:
            self._terminate()
            return
        if self.stop_on_entry:
            self._stop("entry")
        elif self._at_breakpoint():
            self._stop("breakpoint")
        else:
            self._resume(step=False)

    def _on_threads(self, request, args):
        self._respond(request, {"threads": [{"id": THREAD_ID, "name": "main"}]})

    def _on_stackTrace(self, request, args):
        frames = []
        span = self.stopped_at
        if span is not None and self.path is not None:
            frames.append(
                {
                    "id": FRAME_ID,
                    "name": "program",
                    "source": {"name": Path(self.path).name, "path": self.path},
                    "line": span.line,
                    "column": span.column,
                    "endLine": span.end_line,
                    "endColumn": span.end_column,
                }
            )
        self._respond(request, {"stackFrames": frames, "totalFrames": len(frames)})

    def _on_scopes(self, request, args):
        scope = {"name": "State", "variablesReference": VARIABLES_REF, "expensive": False}
        self._respond(request, {"scopes": [scope]})

    def _on_variables(self, request, args):
        state = self.interpreter.state if self.interpreter else {}
        variables = [
            {"name": name, "value": str(value), "variablesReference": 0}
            for name, value in sorted(state.items())
        ]
        self._respond(request, {"variables": variables})

    def _on_evaluate(self, request, args):
        if self.interpreter is None:
            self._respond(request, error="program is not running")
            return
        try:
            node = parse_expression(args.get("expression", ""))
            value = self.interpreter.evaluate(node)
        except (SiplSyntaxError, SiplRuntimeError) as e:
            self._respond(request, error=getattr(e, "message", str(e)))
            return
        self._respond(request, {"result": _format(value), "variablesReference": 0})

    def _on_continue(self, request, args):
        self._respond(request, {"allThreadsContinued": True})
        self._resume(step=False)

    def _on_next(self, request, args):
        self._respond(request)
        self._resume(step=True)

    _on_stepIn = _on_next
    _on_stepOut = _on_next

    def _on_pause(self, request, args):
        self._respond(request, error="pause is not supported, the program runs to the next stop")

    def _on_terminate(self, request, args):
        self._respond(request)
        self._terminate()

    def _on_disconnect(self, request, args):
        self._respond(request)
        self.running = False

    # --- виконання ---

    def _at_breakpoint(self) -> bool:
        assert self.interpreter is not None
        stmt = self.interpreter.next_statement
        return stmt is not None and stmt.span is not None and stmt.span.line in self.breakpoints

    def _stop(self, reason: str, text: str | None = None) -> None:
        assert self.interpreter is not None
        if reason != "exception":
            stmt = self.interpreter.next_statement
            self.stopped_at = stmt.span if stmt else None
        body = {"reason": reason, "threadId": THREAD_ID, "allThreadsStopped": True}
        if text is not None:
            body["text"] = text
            body["description"] = text
        self._event("stopped", body)

    def _resume(self, step: bool) -> None:
        interpreter = self.interpreter
        if interpreter is None or self.error is not None or interpreter.done:
            self._terminate()
            return
        while True:
            span = interpreter.next_statement.span if interpreter.next_statement else None
            try:
                interpreter.step()
            except SiplRuntimeError as e:
                self.error = e
                self.stopped_at = e.span or span
                self._output(f"{e}\n", "stderr")
                self._stop("exception", e.message)
                return
            if interpreter.done:
                self._terminate()
                return
            if step:
                self._stop("step")
                return
            if self._at_breakpoint():
                self._stop("breakpoint")
                return

    def _terminate(self) -> None:
        if self.terminated:
            return
        self.terminated = True
        if self.interpreter is not None and self.error is None:
            for name, value in sorted(self.interpreter.state.items()):
                self._output(f"{name} = {value}\n")
        # same codes as the CLI: 3 is a runtime error
        self._event("exited", {"exitCode": 0 if self.error is None else 3})
        self._event("terminated")


def main() -> int:
    import sys

    if hasattr(sys, "set_int_max_str_digits"):
        sys.set_int_max_str_digits(0)
    DebugServer(sys.stdin.buffer, sys.stdout.buffer).serve()
    return 0
