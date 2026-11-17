"""Читання і запис повідомлень DAP.

Кожне повідомлення це заголовки, порожній рядок і тіло JSON:

    Content-Length: 52\r\n
    \r\n
    {"seq": 1, "type": "request", "command": "initialize"}
"""

from __future__ import annotations

import json
from typing import Any, BinaryIO


class ProtocolError(Exception):
    pass


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """Прочитати одне повідомлення. None, якщо потік закінчився."""
    length = None
    while True:
        line = stream.readline()
        if not line:
            if length is None:
                return None
            raise ProtocolError("stream ended inside headers")
        line = line.rstrip(b"\r\n")
        if not line:
            break
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            try:
                length = int(value.strip())
            except ValueError:
                raise ProtocolError(f"bad Content-Length: {value!r}") from None
    if length is None:
        raise ProtocolError("no Content-Length header")

    body = stream.read(length)
    if len(body) < length:
        raise ProtocolError("stream ended inside body")
    try:
        message = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError(f"bad message body: {error}") from None
    if not isinstance(message, dict):
        raise ProtocolError("message is not an object")
    return message


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body))
    stream.write(body)
    stream.flush()
