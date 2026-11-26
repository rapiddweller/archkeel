# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Hostile requests to the Explorer MCP tools (#1001): a typed error, never a crash or a leak."""

import asyncio
import importlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from archkeel import explorer_mcp
from archkeel.explorer_queries import populate, query
from archkeel.explorer_store import SnapshotIdentity, publish_snapshot
from archkeel.explorer_stories import list_stories, read_story, save_story

SECRET = "TOP-SECRET-OUTSIDE-THE-ROOT"
BAD_PATHS = ["../outside.py", "/etc/hosts", "link/secret.py", "a.py/../../outside.py"]


@pytest.fixture
def scan(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """A snapshot whose evidence names files inside the root and four ways out of it."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("import b\n")
    (tmp_path / "outside.py").write_text(SECRET + "\n")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "secret.py").write_text(SECRET + "\n")
    os.symlink(outside, root / "link")
    evidence = [{"path": "a.py", "line": 1}] + [{"path": name, "line": 1} for name in BAD_PATHS]
    topology = {
        "version": 1,
        "complete": True,
        "truncated": False,
        "gaps": [],
        "components": [],
        "modules": [{"name": name, "component": None, "path": "a.py"} for name in ("a", "b")],
        "edges": [
            {
                "id": "edge",
                "source": "a",
                "target": "b",
                "resolution": "resolved",
                "evidence": evidence,
            }
        ],
    }

    def write(db: sqlite3.Connection) -> None:
        populate(db, topology, root)

    path = tmp_path / "cache" / "sample.sqlite"
    publish_snapshot(path, SnapshotIdentity("rev", "contract", "tree"), write, "complete")
    answer: Any = query(path, root, "evidence", {"relation": "relation:module_import:edge"})
    references = {item["path"]: item["reference"] for item in answer["items"]}
    return path, root, references


def _nested(depth: int) -> Any:
    value: Any = "x"
    for _ in range(depth):
        value = {"a": value}
    return value


NESTED = _nested(5000)
# The client cannot encode more than about a hundred levels; a deeper one is a raw-frame matter.
WIRE_NESTED = _nested(90)

HOSTILE_VALUES: list[Any] = [
    None,
    True,
    -1,
    0,
    2**63,
    1.5,
    float("inf"),
    "9" * 11,
    "a\x00b",
    "x" * 5000,
    "x" * (8 << 20),
    [],
    ["a"] * 100_000,
    {},
    NESTED,
]

OPERATIONS: dict[str, dict[str, Any]] = {
    "overview": {"parent": "system", "cursor": "", "limit": 5},
    "map": {"parent": "system", "view": "components", "cursor": "", "limit": 5, "focus": ""},
    "children": {"parent": "system", "cursor": "", "limit": 5},
    "search": {"text": "a", "cursor": "", "limit": 5, "parent": ""},
    "relations": {"element": "module:a", "direction": "both", "cursor": "", "limit": 5},
    "evidence": {"relation": "relation:module_import:edge", "limit": 5, "cursor": ""},
    "source": {"reference": "x", "limit": 5, "start": 1},
    "story": {"id": "x"},
    "verdict": {},
    "findings": {"rule": "", "component": "", "cursor": "", "limit": 5},
    "unknowns": {"kind": "", "cursor": "", "limit": 5},
    "call_resolution": {"element": "", "status": "", "provenance": "", "call_id": "", "limit": 5},
}


def test_a_wrong_typed_or_huge_argument_gives_value_error_in_bounded_time(
    scan: tuple[Path, Path, dict[str, str]],
) -> None:
    """Each argument of each operation, with each hostile value, is refused or answered."""
    path, root, _ = scan
    started = time.monotonic()
    for operation, good in OPERATIONS.items():
        for field in good:
            for value in HOSTILE_VALUES:
                try:
                    query(path, root, operation, good | {field: value})
                except ValueError:
                    pass  # the typed refusal
    assert time.monotonic() - started < 120


def test_an_unknown_operation_and_extra_arguments_are_refused(
    scan: tuple[Path, Path, dict[str, str]],
) -> None:
    path, root, _ = scan
    for name in ["", "drop", "../verdict", "overview\x00", "x" * 10_000, "__class__"]:
        with pytest.raises(ValueError):
            query(path, root, name, {})
    query(path, root, "overview", {"limit": 1, "unexpected": NESTED})


def test_a_source_path_outside_the_root_is_never_read(
    scan: tuple[Path, Path, dict[str, str]],
) -> None:
    path, root, references = scan
    assert query(path, root, "source", {"reference": references["a.py"]})["lines"] == ["import b"]
    for name in BAD_PATHS:
        try:
            answer = query(path, root, "source", {"reference": references[name]})
        except ValueError:
            continue
        assert SECRET not in json.dumps(answer), name


def test_a_story_id_or_spec_cannot_leave_the_story_folder(
    scan: tuple[Path, Path, dict[str, str]],
) -> None:
    path, root, _ = scan
    for story_id in ["../outside", "/etc/hosts", "a/b", "", "x" * 10_000, "a\x00b", "..", "."]:
        with pytest.raises(ValueError):
            read_story(root, path, story_id)
    for spec in [
        {},
        {"id": "../x"},
        {"id": "ok", "steps": NESTED},
        {"id": "ok", "x": "x" * (4 << 20)},
    ]:
        try:
            save_story(root, path, spec)
        except ValueError:
            pass
    assert not (root.parent / "x.story.json").exists()
    list_stories(root, path)


def _fastmcp() -> Any:
    """The fastmcp module. In CI a missing extra fails: a skip would hide the protocol tests."""
    try:
        return importlib.import_module("fastmcp")
    except ModuleNotFoundError:
        if os.environ.get("CI"):
            pytest.fail("fastmcp is missing: the CI job must run `uv sync --locked --extra mcp`")
        pytest.skip("fastmcp is not installed (the mcp extra)")


def _server(path: Path, root: Path) -> Any:
    fastmcp = _fastmcp()
    server = fastmcp.FastMCP("hostile")
    explorer_mcp._query_tools(server, path, root)
    explorer_mcp._verdict_tools(server, path, root)
    explorer_mcp._story_tools(server, path, root)
    explorer_mcp._resolution_tools(server, path, root)
    return server


def test_the_protocol_layer_answers_each_hostile_call_with_an_error_and_stays_up(
    scan: tuple[Path, Path, dict[str, str]],
) -> None:
    path, root, _ = scan
    fastmcp = _fastmcp()
    server = _server(path, root)
    calls: list[tuple[str, dict[str, Any]]] = [
        ("no_such_tool", {}),
        ("overview", {"limit": "many"}),
        ("overview", {"limit": 10**30}),
        ("overview", {"parent": {"a": 1}}),
        ("overview", {"parent": "x" * (4 << 20)}),
        ("overview", {"unknown_argument": 1}),
        ("search", {}),
        ("search", {"text": None}),
        ("source", {"reference": ["a"]}),
        ("source", {"reference": "../../etc/hosts", "start": "one"}),
        ("story_read", {"id": "../outside"}),
        ("story_save", {"spec": "not an object"}),
        ("story_save", {"spec": WIRE_NESTED}),
        ("verdict", {"unexpected": 1}),
    ]

    async def drive() -> None:
        async with fastmcp.Client(server) as client:
            for name, arguments in calls:
                try:
                    result = await client.call_tool(name, arguments, raise_on_error=False)
                except Exception as error:  # noqa: BLE001 - the client raises its own error types
                    assert type(error).__module__.split(".")[0] in {"fastmcp", "mcp"}, error
                    continue
                assert result.is_error, (name, arguments)
            # The session still works, and many requests in a row stay bounded.
            started = time.monotonic()
            for _ in range(300):
                answer = await client.call_tool("overview", {"limit": 1})
                assert not answer.is_error
            assert time.monotonic() - started < 120

    asyncio.run(drive())


def test_raw_frames_on_stdio_never_stop_the_server_or_grow_its_memory(
    scan: tuple[Path, Path, dict[str, str]],
) -> None:
    """Malformed, truncated, oversized and deeply nested frames; then a valid call still works."""
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    _fastmcp()
    path, root, _ = scan
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "hostile", "version": "0"},
        },
    }
    hostile = [
        b"\n",
        b"not json\n",
        b'{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"overview"\n',
        b"\xff\xfe\x00\n",
        b"[]\n",
        b"null\n",
        b'{"jsonrpc":"2.0","id":3}\n',
        b'{"jsonrpc":"2.0","id":4,"method":"nope"}\n',
        b'{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"overview","arguments":'
        + b"[" * 200_000
        + b"]" * 200_000
        + b"}}\n",
        b'{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"overview","arguments":'
        b'{"parent":"' + b"x" * (16 << 20) + b'"}}}\n',
    ]
    call = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": "overview", "arguments": {"limit": 1}},
    }
    frames = [
        json.dumps(initialize).encode() + b"\n",
        b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n',
        *hostile,
        json.dumps(call).encode() + b"\n",
    ]
    process = subprocess.Popen(  # noqa: S603 - the interpreter and our own module
        [
            sys.executable,
            "-m",
            "archkeel.explorer_mcp",
            "--snapshot",
            str(path),
            "--root",
            str(root),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdin is not None and process.stdout is not None
    answers: list[dict[str, Any]] = []

    def read() -> None:
        for line in process.stdout:  # type: ignore[union-attr]
            if line.startswith(b"{"):
                answers.append(json.loads(line))

    def write() -> None:
        try:
            for frame in frames:
                process.stdin.write(frame)  # type: ignore[union-attr]
                process.stdin.flush()  # type: ignore[union-attr]
        except (BrokenPipeError, ValueError):
            pass  # the server stopped or the test killed it: the wait below reports it

    # Writing runs in a thread: a server that stops reading must end at the deadline, not hang.
    for target in (read, write):
        threading.Thread(target=target, daemon=True).start()
    deadline = time.monotonic() + 120
    try:
        # The input stays open: at its end the server closes by design.
        while not any(a.get("id") == 99 for a in answers) and time.monotonic() < deadline:
            assert process.poll() is None, f"the server stopped: {answers[-3:]}"
            time.sleep(0.05)
    finally:
        process.kill()
        # wait4 reaps this child only, so its usage is the server's and not that of earlier tests.
        _, _, usage = os.wait4(process.pid, 0)
    assert any(a.get("id") == 99 and "result" in a for a in answers), answers[-3:]
    megabytes = usage.ru_maxrss / (1 << 20 if sys.platform == "darwin" else 1 << 10)
    assert megabytes < 1024, megabytes  # a 16 MiB frame and 200 000 levels peak near 170 MiB
