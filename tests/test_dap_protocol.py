import io

import pytest

from sipl.dap.protocol import ProtocolError, read_message, write_message


def framed(body: bytes) -> bytes:
    return b"Content-Length: %d\r\n\r\n" % len(body) + body


def test_write_then_read():
    stream = io.BytesIO()
    write_message(stream, {"seq": 1, "type": "request", "command": "initialize"})
    write_message(stream, {"seq": 2, "type": "event", "event": "output", "body": {"x": "ї"}})
    stream.seek(0)
    assert read_message(stream) == {"seq": 1, "type": "request", "command": "initialize"}
    assert read_message(stream)["body"] == {"x": "ї"}
    assert read_message(stream) is None


def test_length_counts_bytes_not_chars():
    stream = io.BytesIO()
    write_message(stream, {"a": "ґ"})
    assert stream.getvalue().startswith(b"Content-Length: 11\r\n\r\n")


def test_other_headers_are_ignored():
    body = b'{"seq": 3}'
    data = b"Content-Type: application/json\r\ncontent-length: %d\r\n\r\n" % len(body) + body
    assert read_message(io.BytesIO(data)) == {"seq": 3}


@pytest.mark.parametrize(
    "data",
    [
        b"Content-Length: 5\r\n",
        b"Content-Length: x\r\n\r\n{}",
        b"Foo: 1\r\n\r\n{}",
        b"Content-Length: 10\r\n\r\n{}",
        framed(b"not json"),
        framed(b"[1, 2]"),
        framed(b"\xff\xfe"),
    ],
)
def test_bad_input(data):
    with pytest.raises(ProtocolError):
        read_message(io.BytesIO(data))
