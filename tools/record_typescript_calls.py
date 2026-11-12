# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record Python collection calls from an unchanged origin/main worktree (AD-394).

Run ``uv sync --locked`` in that worktree first, then run from the deletion checkout::

    uv run python tools/record_typescript_calls.py --main-worktree PATH TEST_FILE ...

Only the worktree's Python analyzer supplies replies. The candidate tests still compare
native facts with them. The archive header records the main SHA and the archive digest.
"""

from __future__ import annotations

import argparse
import atexit
import gzip
import hashlib
import importlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from archkeel.ir.protocol import CollectionRequest, ProtocolVersion

ENV = "ARCHKEEL_RECORD_MAIN_WORKTREE"
HEADER = "main-calls.json"
ARCHIVE = "main-calls.zip"
_PROCESS: subprocess.Popen[str] | None = None
_REPLIES: dict[str, bytes] = {}
_DIRECTORY: Path | None = None
_PRODUCER: dict[str, str] = {}


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _serve(root: Path) -> None:
    from archkeel.ir.facts_codec import decode_request, encode_response
    from archkeel.ir.protocol import CollectionResponse

    producer = importlib.import_module("archkeel.analyzer.typescript.collect")
    assert Path(producer.__file__).resolve() == root / "src/archkeel/analyzer/typescript/collect.py"
    print(
        json.dumps(
            {"main_sha": _git(root, "rev-parse", "HEAD"), "python": platform.python_version()}
        ),
        flush=True,
    )
    for line in sys.stdin:
        request = decode_request(bytes.fromhex(json.loads(line)))
        reply = encode_response(
            CollectionResponse(producer.collect(request), request.protocol_version)
        )
        print(json.dumps(reply.hex()), flush=True)


def capture(directory: Path, identity: str, request: CollectionRequest) -> bytes:
    from archkeel.ir.facts_codec import encode_request

    global _PROCESS, _DIRECTORY
    root = Path(os.environ[ENV]).resolve()
    _DIRECTORY = directory
    if _PROCESS is None:
        _PROCESS = subprocess.Popen(
            [
                str(root / ".venv/bin/python"),
                "-I",
                "-B",
                str(Path(__file__).resolve()),
                "--serve",
                str(root),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        assert _PROCESS.stdout is not None
        _PRODUCER.update(json.loads(_PROCESS.stdout.readline()))
        atexit.register(_finish)
    assert _PROCESS.stdin is not None and _PROCESS.stdout is not None
    if request.scope.exclude_test_sources:
        request = replace(request, protocol_version=ProtocolVersion.V9)
    _PROCESS.stdin.write(json.dumps(encode_request(request).hex()) + "\n")
    _PROCESS.stdin.flush()
    line = _PROCESS.stdout.readline()
    assert line, f"typescript_oracle_producer_failed: {identity}"
    reply = bytes.fromhex(json.loads(line))
    assert identity not in _REPLIES, f"typescript_oracle_duplicate_key: {identity}"
    _REPLIES[identity] = reply
    return reply


def _finish() -> None:
    if _PROCESS is not None:
        assert _PROCESS.stdin is not None
        _PROCESS.stdin.close()
        assert _PROCESS.wait(timeout=30) == 0, "typescript_oracle_producer_failed"
    if not _REPLIES:
        return
    assert _DIRECTORY is not None
    main = _git(Path(os.environ[ENV]), "rev-parse", "HEAD")
    assert main == _PRODUCER["main_sha"], "typescript_oracle_main_changed"
    header = _DIRECTORY / HEADER
    archive = _DIRECTORY / ARCHIVE
    entries: dict = {}
    members: dict[str, bytes] = {}
    if header.exists():
        old = json.loads(header.read_bytes())
        assert old["main_sha"] == main, "typescript_oracle_main_changed: record a new snapshot"
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == old["content_digest"]
        entries = old["replies"]
        with ZipFile(archive) as stored:
            members = {name: stored.read(name) for name in stored.namelist()}
    for identity, reply in _REPLIES.items():
        name = hashlib.sha256(identity.encode()).hexdigest() + ".bin"
        members[name] = gzip.compress(reply, mtime=0)
        entries[identity] = {"file": name, "sha256": hashlib.sha256(members[name]).hexdigest()}
    with ZipFile(archive, "w", compression=ZIP_STORED) as stored:
        for name, data in sorted(members.items()):
            stored.writestr(ZipInfo(name), data)
    header.write_text(
        json.dumps(
            {
                **_PRODUCER,
                "archive": ARCHIVE,
                "content_digest": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "replies": entries,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    print(
        f"Recorded {len(_REPLIES)} calls from main {main}; {len(entries)} keys in {archive}.",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-worktree", type=Path)
    parser.add_argument("--serve", type=Path)
    parser.add_argument("tests", nargs="*")
    args = parser.parse_args()
    if args.serve:
        _serve(args.serve.resolve())
        return 0
    assert args.main_worktree is not None and args.tests, "supply --main-worktree and test files"
    root = args.main_worktree.resolve()
    assert _git(root, "rev-parse", "HEAD") == _git(root, "rev-parse", "origin/main")
    assert not _git(root, "status", "--porcelain", "--untracked-files=no")
    assert (root / "src/archkeel/analyzer/typescript/collect.py").is_file()
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-n", "0", *args.tests],
        env={**os.environ, ENV: str(root)},
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
