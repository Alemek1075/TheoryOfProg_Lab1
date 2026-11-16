from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict

from . import ast
from .interpreter import (
    DEFAULT_STEP_LIMIT,
    BeforeStatement,
    ConditionChecked,
    Finished,
    Interpreter,
    SiplRuntimeError,
    VariableChanged,
)
from .parser import SiplSyntaxError, parse

# Exit codes. They are part of the CLI contract, see docs/cli.md.
EXIT_OK = 0
EXIT_SYNTAX_ERROR = 1
EXIT_USAGE = 2  # same code argparse uses for a bad command line
EXIT_RUNTIME_ERROR = 3

_ASSIGNMENT = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=(-?[0-9]+)")


def main(argv: list[str] | None = None) -> int:
    # Python 3.11+ refuses to print integers longer than 4300 digits by default,
    # and a SIPL program gets there with a few multiplications in a loop.
    if hasattr(sys, "set_int_max_str_digits"):
        sys.set_int_max_str_digits(0)
    # The Windows console encoding cannot show ¬ or ∨. Print them escaped instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")

    args = _arguments().parse_args(argv)
    try:
        text = _read(args.file)
    except (OSError, UnicodeDecodeError) as e:
        reason = e.strerror if isinstance(e, OSError) and e.strerror else "not a UTF-8 text"
        return _error(args, None, EXIT_USAGE, "file_error", f"cannot read file: {reason}", None)
    try:
        program = parse(text)
    except SiplSyntaxError as e:
        return _error(args, text, EXIT_SYNTAX_ERROR, "syntax_error", e.message, e.span)
    return args.command(args, text, program)


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sipl", description="Tools for the SIPL language.")
    commands = parser.add_subparsers(dest="name", required=True, metavar="command")

    def command(name, function, help):
        sub = commands.add_parser(name, help=help, description=help)
        sub.set_defaults(command=function)
        sub.add_argument("file", help="program file, or - to read from stdin")
        sub.add_argument("--json", action="store_true", help="print the result as JSON")
        return sub

    command("check", _check, "check the syntax of a program")
    command("parse", _parse, "print the syntax tree of a program")
    for name, function, help in (
        ("run", _run, "run a program and print the final state"),
        ("trace", _trace, "run a program and print every step"),
    ):
        sub = command(name, function, help)
        sub.add_argument(
            "state",
            nargs="*",
            type=_assignment,
            metavar="NAME=NUMBER",
            help="initial value of a variable, for example X=2",
        )
        sub.add_argument(
            "--step-limit",
            type=_positive,
            default=DEFAULT_STEP_LIMIT,
            metavar="N",
            help=f"stop after N steps (default {DEFAULT_STEP_LIMIT})",
        )
    return parser


def _assignment(text: str) -> tuple[str, int]:
    match = _ASSIGNMENT.fullmatch(text)
    if not match:
        raise argparse.ArgumentTypeError(f"expected NAME=NUMBER, got '{text}'")
    return match.group(1), int(match.group(2))


def _positive(text: str) -> int:
    if not text.isdigit() or int(text) == 0:
        raise argparse.ArgumentTypeError(f"expected a positive number, got '{text}'")
    return int(text)


def _read(path: str) -> str:
    # utf-8-sig drops the BOM that Windows editors like to add.
    # Line ends are kept as they are, so the offsets in spans match the file.
    if path == "-":
        return sys.stdin.buffer.read().decode("utf-8-sig")
    with open(path, encoding="utf-8-sig", newline="") as file:
        return file.read()


def _check(args, text, program) -> int:
    if args.json:
        _print_json({"ok": True})
    else:
        print("ok")
    return EXIT_OK


def _parse(args, text, program) -> int:
    try:
        if args.json:
            _print_json({"ok": True, "ast": ast.to_dict(program)})
        else:
            print("\n".join(_tree_lines(program)))
    except RecursionError:
        message = "program is nested too deeply to print"
        return _error(args, None, EXIT_USAGE, "too_deep", message, None)
    return EXIT_OK


def _run(args, text, program) -> int:
    interpreter = Interpreter(program, dict(args.state), args.step_limit)
    try:
        interpreter.run()
    except SiplRuntimeError as e:
        extra = {"state": _sorted(interpreter.state), "steps": interpreter.steps}
        return _error(args, text, EXIT_RUNTIME_ERROR, e.code, e.message, e.span, extra)
    if args.json:
        _print_json({"ok": True, "state": _sorted(interpreter.state), "steps": interpreter.steps})
    else:
        for name, value in _sorted(interpreter.state).items():
            print(f"{name} = {value}")
    return EXIT_OK


def _trace(args, text, program) -> int:
    events = []
    interpreter = Interpreter(program, dict(args.state), args.step_limit)
    interpreter.subscribe(events.append)
    error = None
    try:
        interpreter.run()
    except SiplRuntimeError as e:
        error = e

    if args.json:
        payload = {"ok": error is None, "events": [event.to_dict() for event in events]}
        if error:
            payload["error"] = _error_dict(error.code, error.message, error.span)
        _print_json(payload)
    else:
        for line in _trace_lines(events, text):
            print(line)
        if error:
            _print_error(args, text, error.message, error.span)
    return EXIT_RUNTIME_ERROR if error else EXIT_OK


def _error(args, text, exit_code, kind, message, span, extra=None) -> int:
    if args.json:
        _print_json({"ok": False, "error": _error_dict(kind, message, span), **(extra or {})})
    else:
        _print_error(args, text, message, span)
    return exit_code


def _error_dict(kind, message, span) -> dict:
    return {"kind": kind, "message": message, "span": asdict(span) if span else None}


def _print_error(args, text, message, span) -> None:
    where = f"{args.file}:{span.line}:{span.column}" if span else args.file
    print(f"{where}: error: {message}", file=sys.stderr)
    lines = text.splitlines() if text and span else []
    if span and span.line <= len(lines):
        line = lines[span.line - 1]
        # tabs stay tabs so the mark ends up under the right character
        padding = "".join("\t" if ch == "\t" else " " for ch in line[: span.column - 1])
        print(f"  {line}", file=sys.stderr)
        print(f"  {padding}^", file=sys.stderr)


def _print_json(payload: dict) -> None:
    print(json.dumps(payload))


def _sorted(state: dict[str, int]) -> dict[str, int]:
    return dict(sorted(state.items()))


def _tree_lines(node: ast.Node, depth: int = 0):
    values, children = [], []
    for name, value in ast.fields_of(node):
        (children if isinstance(value, ast.Node) else values).append(value)
    yield "  " * depth + " ".join([type(node).__name__, *map(str, values)])
    for child in children:
        yield from _tree_lines(child, depth + 1)


def _trace_lines(events, text):
    for event in events:
        if isinstance(event, VariableChanged):
            old = "-" if event.old is None else event.old
            note = f"{event.name}: {old} -> {event.new}"
            yield _trace_line(event.step, event.statement.span, text, note)
        elif isinstance(event, ConditionChecked):
            note = "true" if event.result else "false"
            yield _trace_line(event.step, event.statement.cond.span, text, note)
        elif isinstance(event, BeforeStatement) and isinstance(event.statement, ast.Skip):
            yield _trace_line(event.step, event.statement.span, text, "")
        elif isinstance(event, Finished):
            yield f"finished in {event.step} steps"
            for name, value in _sorted(event.state).items():
                yield f"{name} = {value}"


def _trace_line(step, span, text, note) -> str:
    source = " ".join(text[span.start : span.end].split())
    where = f"{span.line}:{span.column}"
    return f"{step:>5}  {where:<7} {source:<24} {note}".rstrip()
