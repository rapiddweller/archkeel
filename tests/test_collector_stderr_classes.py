# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-268: equivalence classes of collector stderr, exit status and stdout."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from test_collection_protocol import _request, _response

from archkeel.analyzer.process import ProcessCollector
from archkeel.ir.facts_codec import decode_request
from archkeel.ir.protocol import CollectionError

LIMIT = 1_000
LINES_REPORTED = 20
END = "RealError: the end"


def _text(size: int, line: Callable[[int], str]) -> bytes:
    """A stderr stream of exactly `size` bytes that ends with the real error."""
    tail = (END).encode()
    if size <= len(tail):
        return tail[-size:] if size else b""
    body = bytearray()
    index = 0
    while len(body) < size - len(tail):
        body += line(index).encode()
        index += 1
    return bytes(body[: size - len(tail)]) + tail


PATTERNS: dict[str, Callable[[int], str]] = {
    "short_lines": lambda i: f"line {i}\n",
    "one_long_line": lambda i: "x" * 97 + " ",
    "crlf_lines": lambda i: f"line {i}\r\n",
    "two_byte_chars": lambda i: "é" * 7 + "\n",
    "three_byte_chars": lambda i: "€€€ " + str(i) + "\n",
    "four_byte_chars": lambda i: "😀" * 3 + "\n",
    "invalid_utf8": lambda i: "ok\n",  # the fault bytes are added below
    "blank_lines": lambda i: "\n\n  \n",
}
# Sizes: nothing, one byte, around the limit, and several times the limit.
SIZES = [0, 1, LIMIT - 1, LIMIT, LIMIT + 1, 5 * LIMIT + 3]


def _stream(pattern: str, size: int) -> bytes:
    data = _text(size, PATTERNS[pattern])
    if pattern == "invalid_utf8" and len(data) > 40:
        data = data[:20] + b"\xff\xfe\xc3" + data[23:]
    return data


def _collector(
    tmp_path: Path,
    stderr: bytes,
    *,
    exit_code: int,
    stdout: str,
    chunk: int = 0,
    **limits: float,
) -> ProcessCollector:
    stream = tmp_path / "stderr.bin"
    stream.write_bytes(stderr)
    code = (
        "import sys, time\n"
        "sys.stdin.read()\n"
        f"data = open({str(stream)!r}, 'rb').read()\n"
        f"step = {chunk} or max(len(data), 1)\n"
        "for start in range(0, len(data), step):\n"
        "    sys.stderr.buffer.write(data[start:start + step]); sys.stderr.buffer.flush()\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.exit({exit_code})\n"
    )
    return ProcessCollector((sys.executable, "-B", "-c", code), stderr_limit_bytes=LIMIT, **limits)


def _request_for(tmp_path: Path):
    request = decode_request(_request())
    return replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))


def _expected_message(stderr: bytes, exit_code: int) -> str:
    """The specification of AD-268: the last 1,000 bytes, then the last 20 lines."""
    tail = stderr[-LIMIT:]
    lines = tail.decode("utf-8", errors="replace").strip().splitlines()
    return f"Collector exited {exit_code}: " + "\n".join(lines[-LINES_REPORTED:])


VALID = json.dumps(_response())


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("pattern", PATTERNS)
def test_a_valid_answer_succeeds_for_every_stderr_size_and_shape(
    tmp_path: Path, pattern: str, size: int
) -> None:
    collector = _collector(tmp_path, _stream(pattern, size), exit_code=0, stdout=VALID)
    result = collector.collect_response(_request_for(tmp_path))
    assert not isinstance(result, CollectionError), result


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("pattern", PATTERNS)
def test_a_failed_collector_reports_exactly_the_end_of_its_stderr(
    tmp_path: Path, pattern: str, size: int
) -> None:
    stderr = _stream(pattern, size)
    collector = _collector(tmp_path, stderr, exit_code=3, stdout="")
    result = collector.collect_response(_request_for(tmp_path))
    assert isinstance(result, CollectionError)
    assert result.kind == "execution_error"
    assert result.message == _expected_message(stderr, 3)
    assert "limit" not in result.message
    if size > len(END):
        assert result.message.endswith(END)


@pytest.mark.parametrize("chunk", [1, 7, 64, LIMIT - 1, LIMIT, LIMIT + 1, 4096])
def test_the_kept_tail_does_not_depend_on_how_the_collector_chunks_its_writes(
    tmp_path: Path, chunk: int
) -> None:
    stderr = _stream("short_lines", 5 * LIMIT + 3)
    collector = _collector(tmp_path, stderr, exit_code=4, stdout="", chunk=chunk)
    result = collector.collect_response(_request_for(tmp_path))
    assert isinstance(result, CollectionError)
    assert result.message == _expected_message(stderr, 4)


@pytest.mark.parametrize("exit_code", [1, 2, 3, 127, 255])
def test_every_nonzero_exit_code_is_named(tmp_path: Path, exit_code: int) -> None:
    collector = _collector(tmp_path, b"boom", exit_code=exit_code, stdout=VALID)
    result = collector.collect_response(_request_for(tmp_path))
    assert isinstance(result, CollectionError)
    assert result.message == f"Collector exited {exit_code}: boom"


def test_a_failed_collector_with_no_stderr_still_names_its_exit_code(tmp_path: Path) -> None:
    collector = _collector(tmp_path, b"", exit_code=5, stdout="")
    result = collector.collect_response(_request_for(tmp_path))
    assert isinstance(result, CollectionError)
    assert result.message == "Collector exited 5: "


@pytest.mark.parametrize("stdout", ["", "not json", "{}", "[]"])
def test_a_bad_answer_with_exit_zero_is_a_protocol_error_whatever_stderr_holds(
    tmp_path: Path, stdout: str
) -> None:
    collector = _collector(tmp_path, _stream("short_lines", 5 * LIMIT), exit_code=0, stdout=stdout)
    result = collector.collect_response(_request_for(tmp_path))
    assert isinstance(result, CollectionError)
    assert result.kind == "protocol_error"


@pytest.mark.parametrize("exit_code", [0, 3])
def test_an_oversized_stdout_names_its_own_limit_not_the_stderr_size(
    tmp_path: Path, exit_code: int
) -> None:
    collector = _collector(
        tmp_path,
        _stream("short_lines", 5 * LIMIT),
        exit_code=exit_code,
        stdout="x" * 5_000,
        output_limit_bytes=1_000,
    )
    result = collector.collect_response(_request_for(tmp_path))
    assert isinstance(result, CollectionError)
    assert result.kind == "protocol_error"
    assert "collector_output_limit_bytes" in result.message


def test_the_default_limit_keeps_the_last_64_kib_of_a_multi_megabyte_stream(
    tmp_path: Path,
) -> None:
    stderr = _stream("short_lines", 3_000_000)
    stream = tmp_path / "stderr.bin"
    stream.write_bytes(stderr)
    code = (
        "import sys\nsys.stdin.read()\n"
        f"sys.stderr.buffer.write(open({str(stream)!r}, 'rb').read())\nsys.exit(9)\n"
    )
    started = time.perf_counter()
    result = ProcessCollector((sys.executable, "-B", "-c", code)).collect_response(
        _request_for(tmp_path)
    )
    assert time.perf_counter() - started < 20
    assert isinstance(result, CollectionError)
    assert result.message.startswith("Collector exited 9:")
    assert result.message.endswith(END)


def test_a_hung_collector_with_endless_stderr_still_times_out(tmp_path: Path) -> None:
    code = (
        "import sys, time\nsys.stdin.read()\n"
        "while True:\n    sys.stderr.write('x' * 65536); sys.stderr.flush()\n"
    )
    started = time.perf_counter()
    result = ProcessCollector(
        (sys.executable, "-B", "-c", code), timeout_seconds=1
    ).collect_response(_request_for(tmp_path))
    assert time.perf_counter() - started < 15
    assert isinstance(result, CollectionError)
    assert result.kind == "timeout"
