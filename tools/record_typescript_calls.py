# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record public test inputs with an unchanged origin/main Python analyzer.

Run with --main-worktree PATH and pytest file names. Generated fixtures stay inside this
checkout's ignored test-artifacts directory. Each test has one compressed archive member.
Only the named public repository may be supplied as an external source root.
"""

from __future__ import annotations

import argparse
import atexit
import base64
import hashlib
import json
import os
import subprocess
import sys
import zlib
from dataclasses import replace
from functools import cache
from pathlib import Path
from zipfile import ZIP_LZMA, ZipFile, ZipInfo

from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import ProtocolVersion

ROOT = Path(__file__).resolve().parents[1]
ENV = "ARCHKEEL_RECORD_MAIN_WORKTREE"
PUBLIC = {"excalidraw": "github.com/excalidraw/excalidraw"}
_PROCESS: subprocess.Popen[str] | None = None
_CALLS: dict[str, dict[str, list[dict]]] = {}
_SOURCES: dict[str, set[str]] = {}
_PRODUCER: dict[str, str] = {}
_DIRECTORY: Path | None = None


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


@cache
def _check_public(public: Path, remote: str) -> None:
    origin = _git(public, "remote", "get-url", "origin").removesuffix(".git")
    assert origin in {f"https://{remote}", f"git@{remote.replace('/', ':', 1)}"}, (
        "typescript_oracle_public_origin_mismatch"
    )
    assert not _git(public, "status", "--porcelain", "--untracked-files=all"), (
        "typescript_oracle_public_tree_changed"
    )


def source_name(path: Path) -> str:
    """Reject external roots and symlink escapes before the producer reads them."""
    path = path.resolve()
    if path.is_relative_to(ROOT):
        return "repository"
    for name, remote in PUBLIC.items():
        folder = os.environ.get("ARCHKEEL_PUBLIC_" + name.upper())
        if folder and path.is_relative_to(public := Path(folder).resolve()):
            _check_public(public, remote)
            return name
    raise AssertionError("typescript_oracle_source_outside_public_roots")


def pack_reply(data: bytes) -> dict:
    compressed = data[:1] == b"x"
    plain = zlib.decompress(data) if compressed else data
    if compressed:
        assert zlib.compress(plain, level=1) == data, "typescript_oracle_wire_compression_changed"
    return {"text": plain.decode("utf-8"), "compressed": compressed}


def source_tree(root: Path) -> str:
    """Check links before a producer can read a selected source tree."""
    origin = source_name(root)
    visited: set[Path] = set()
    for directory, folders, files in os.walk(root, followlinks=True):
        actual = Path(directory).resolve()
        if actual in visited:
            folders.clear()
            continue
        visited.add(actual)
        folders[:] = [name for name in folders if name not in {".git", ".venv", "__pycache__"}]
        if Path(directory) == ROOT:
            folders[:] = [name for name in folders if name != "test-artifacts"]
        if Path(directory) == ROOT / "native":
            folders[:] = [name for name in folders if name != "target"]
        for name in [*folders, *files]:
            path = Path(directory) / name
            if path.is_symlink():
                try:
                    source_name(path)
                except RuntimeError:
                    pass  # An unresolvable link cycle has no readable source bytes.
    return origin


def capture(directory: Path, test: str, kind: str, arguments: tuple) -> bytes:
    global _PROCESS, _DIRECTORY
    _DIRECTORY = directory
    if kind in {"collect", "records"}:
        request = arguments[0]
        origin = source_tree(Path(request.snapshot.root))
        if request.scope.exclude_test_sources:
            request = replace(request, protocol_version=ProtocolVersion.V9)
        sent = [encode_request(request).hex()]
    elif kind in {"locale", "verdict"}:
        origin = source_tree(arguments[0])
        sent = [str(arguments[0]), *arguments[1:]]
    else:
        origin = source_name(arguments[2] if len(arguments) > 2 else ROOT)
        relative = Path(arguments[0])
        assert not relative.is_absolute() and ".." not in relative.parts, (
            "typescript_oracle_source_outside_public_roots"
        )
        sent = [arguments[0], base64.b64encode(arguments[1]).decode()]
    if _PROCESS is None:
        root = Path(os.environ[ENV]).resolve()
        _PROCESS = subprocess.Popen(
            [
                str(root / ".venv/bin/python"),
                "-I",
                "-X",
                "utf8",
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
    _PROCESS.stdin.write(json.dumps({"kind": kind, "arguments": sent}) + "\n")
    _PROCESS.stdin.flush()
    line = _PROCESS.stdout.readline()
    assert line, "typescript_oracle_producer_failed"
    reply = json.loads(line)
    data = base64.b64decode(reply, validate=True)
    _CALLS.setdefault(test, {}).setdefault(kind, []).append(pack_reply(data))
    _SOURCES.setdefault(test, set()).add(origin)
    return data


def _finish() -> None:
    assert _PROCESS is not None and _PROCESS.stdin is not None and _DIRECTORY is not None
    _PROCESS.stdin.close()
    assert _PROCESS.wait(timeout=30) == 0, "typescript_oracle_producer_failed"
    _check_public.cache_clear()
    for sources in _SOURCES.values():
        for name in sources - {"repository"}:
            _check_public(
                Path(os.environ["ARCHKEEL_PUBLIC_" + name.upper()]).resolve(), PUBLIC[name]
            )
    directory = _DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    header, archive = directory / "manifest.json", directory / "public.zip"
    entries: dict = {}
    members: dict[str, bytes] = {}
    if header.exists():
        old = json.loads(header.read_bytes())
        assert old["main_sha"] == _PRODUCER["main_sha"], "typescript_oracle_main_changed"
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == old["content_digest"]
        entries = old["tests"]
        with ZipFile(archive) as stored:
            members = {name: stored.read(name) for name in stored.namelist()}
    for test, values in _CALLS.items():
        name = hashlib.sha256(test.encode()).hexdigest() + ".json"
        members[name] = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        entries[test] = {
            "file": name,
            "sha256": hashlib.sha256(members[name]).hexdigest(),
            "sources": sorted(_SOURCES[test]),
            "calls": sum(map(len, values.values())),
        }
    pending = archive.with_suffix(".pending")
    with ZipFile(pending, "w", compression=ZIP_LZMA) as stored:
        for name, data in sorted(members.items()):
            info = ZipInfo(name)
            info.compress_type = ZIP_LZMA
            stored.writestr(info, data)
    pending.replace(archive)
    header.write_text(
        json.dumps(
            {
                **_PRODUCER,
                "archive": archive.name,
                "content_digest": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "tests": entries,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    print(f"Recorded {len(_CALLS)} public tests; {len(entries)} total.", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-worktree", type=Path)
    parser.add_argument("--serve", type=Path)
    parser.add_argument("tests", nargs="*")
    args = parser.parse_args()
    if args.serve:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from record_typescript_oracle import serve

        serve(args.serve.resolve())
        return 0
    assert args.main_worktree is not None and args.tests
    root = args.main_worktree.resolve()
    sha = _git(root, "rev-parse", "HEAD")
    assert _git(ROOT, "merge-base", sha, "origin/main") == sha
    assert not _git(root, "status", "--porcelain", "--untracked-files=no")
    basetemp = ROOT / "test-artifacts" / ("public-oracle-" + str(os.getpid()))
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {"ARCHKEEL_PRIVATE_UI", "ARCHKEEL_RECORDS_CORPORA", "ARCHKEEL_RECORD_TYPESCRIPT"}
    }
    environment[ENV] = str(root)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-n",
            "0",
            "--basetemp",
            str(basetemp),
            *args.tests,
        ],
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
