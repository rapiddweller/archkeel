# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build the pinned Compass workspace and record the ten analyzer type bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from pathlib import Path
from threading import Timer
from typing import IO
from urllib.parse import unquote, urlparse

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/J-compass"
PINS = FIXTURE / "compass-build"
APP = Path("compass_app/app")
VERSIONS = ("frameworkVersion", "frameworkRevision", "engineRevision", "dartSdkVersion")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def call(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    *,
    capture: bool = False,
) -> bytes:
    return subprocess.run(
        command, cwd=cwd, env=env, check=True, capture_output=capture, timeout=600
    ).stdout


def stage_source(
    temporary: Path, env: dict[str, str], source_repo: Path | None
) -> tuple[Path, str]:
    snapshot = json.loads((FIXTURE / "SNAPSHOT.json").read_text())
    commit = snapshot["commit"]
    if source_repo is None:
        source_repo = temporary / "source"
        call(["git", "init", "--bare", str(source_repo)], temporary, env)
        url = f"https://github.com/{snapshot['repository']}"
        call(["git", "fetch", "--depth=1", url, commit], source_repo, env)
    archive = temporary / "workspace.tar"
    with archive.open("wb") as stream:
        subprocess.run(
            ["git", "archive", "--format=tar", commit],
            cwd=source_repo,
            env=env,
            check=True,
            stdout=stream,
            timeout=600,
        )
    workspace = temporary / "workspace"
    workspace.mkdir()
    with tarfile.open(archive) as bundle:
        bundle.extractall(workspace, filter="data")
    for entry in snapshot["files"]:
        if sha256(workspace / entry["source_path"]) != entry["sha256"]:
            raise ValueError(f"upstream file differs from the Compass pin: {entry['source_path']}")
    return workspace, commit


def package_roots(workspace: Path) -> dict[str, Path]:
    config = workspace / ".dart_tool/package_config.json"
    packages = json.loads(config.read_text())["packages"]
    roots: dict[str, Path] = {}
    for package in packages:
        uri = urlparse(package["rootUri"])
        path = Path(unquote(uri.path))
        roots[package["name"]] = (config.parent / path).resolve()
    return roots


def git_package_digest(root: Path, env: dict[str, str]) -> str:
    prefix = call(["git", "rev-parse", "--show-prefix"], root, env, capture=True)
    relative = prefix.decode().strip().rstrip("/")
    top = call(["git", "rev-parse", "--show-toplevel"], root, env, capture=True)
    repository = Path(top.decode().strip())
    raw = call(
        ["git", "-c", "tar.umask=0002", "archive", "--format=tar", "HEAD", relative],
        repository,
        env,
        capture=True,
    )
    return hashlib.sha256(raw).hexdigest()


def type_subjects() -> Iterator[tuple[str, Path, str, str]]:
    for target in sorted((FIXTURE / "contracts").glob("*.json")):
        entries = json.loads(target.read_text())["declarations"]["uml"]["entities"]
        for entry in entries:
            name = entry["qualified_name"]
            names = name.split(".")
            field = names[-1]
            if field not in {"_log", "_tokenKey"} or "annotation" not in entry:
                continue
            source = Path("lib", *names[1:-2]).with_suffix(".dart")
            yield name, source, field, entry["annotation"]


class Analyzer:
    """The framed Dart language server connection for one build."""

    def __init__(self, stdin: IO[bytes], stdout: IO[bytes]) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self.id = 0

    def send(self, message: dict[str, object]) -> None:
        payload = json.dumps({"jsonrpc": "2.0", **message}).encode()
        self.stdin.write(f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)
        self.stdin.flush()

    def receive(self) -> dict[str, object]:
        header: dict[str, str] = {}
        while (line := self.stdout.readline()).strip():
            name, value = line.decode().split(":", 1)
            header[name.lower()] = value.strip()
        if "content-length" not in header:
            raise ValueError("Dart analyzer closed its stream")
        payload: object = json.loads(self.stdout.read(int(header["content-length"])))
        if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
            raise ValueError("Dart analyzer sent an invalid JSON-RPC object")
        return payload

    def request(self, method: str, params: object) -> object:
        self.id += 1
        self.send({"method": method, "params": params, "id": self.id})
        while True:
            message = self.receive()
            if "method" in message:
                if "id" in message:
                    self.send({"id": message["id"], "result": None})
            elif message.get("id") == self.id:
                if "error" in message:
                    raise ValueError(f"Dart analyzer {method}: {message['error']}")
                return message["result"]


def one_type(
    analyzer: Analyzer,
    app: Path,
    subject: tuple[str, Path, str, str],
    definitions: dict[str, tuple[str, Path]],
) -> dict[str, str | int]:
    name, relative, field, expected = subject
    source = app / relative
    content = source.read_text()
    line, column = next(
        (row, match.start())
        for row, text in enumerate(content.splitlines())
        if (match := re.search(rf"\b{re.escape(field)}\s*=", text))
    )
    uri = source.as_uri()
    analyzer.send(
        {
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {"uri": uri, "languageId": "dart", "version": 1, "text": content}
            },
        }
    )
    position = {"textDocument": {"uri": uri}, "position": {"line": line, "character": column + 1}}
    # Hover waits for analysis of the opened document before type navigation.
    analyzer.request("textDocument/hover", position)
    result = analyzer.request("textDocument/typeDefinition", position)
    analyzer.send({"method": "textDocument/didClose", "params": {"textDocument": {"uri": uri}}})
    definition, target = definitions[expected]
    if isinstance(result, list):
        result = result[0] if len(result) == 1 else None
    if not isinstance(result, dict):
        raise ValueError(f"Dart analyzer did not resolve {name} to {definition}")
    target_uri = result.get("targetUri") or result.get("uri")
    if (
        not isinstance(target_uri, str)
        or Path(unquote(urlparse(target_uri).path)).resolve() != target
    ):
        raise ValueError(f"Dart analyzer did not resolve {name} to {definition}")
    extent = result.get("targetSelectionRange") or result["range"]
    where = extent["start"]
    ended = extent["end"]
    source_line = target.read_text().splitlines()[where["line"]]
    if source_line[where["character"] : ended["character"]] != expected:
        raise ValueError(f"Dart analyzer resolved a different declaration for {name}")
    return {
        "subject": name,
        "source": (APP / relative).as_posix(),
        "line": line + 1,
        "type": expected,
        "definition": definition,
        "definition_line": where["line"] + 1,
        "definition_sha256": sha256(target),
    }


def prove_types(
    flutter: Path, app: Path, roots: dict[str, Path], env: dict[str, str]
) -> list[dict[str, str | int]]:
    definitions = {
        "Logger": ("package:logging/src/logger.dart", roots["logging"] / "lib/src/logger.dart"),
        "String": ("dart:core.String", roots["sky_engine"] / "lib/core/string.dart"),
    }
    dart = flutter.parent / "cache/dart-sdk/bin"
    with subprocess.Popen(
        [str(dart / "dart"), str(dart / "snapshots/analysis_server.dart.snapshot"), "--lsp"],
        cwd=app,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as process:
        timer = Timer(120, process.kill)
        timer.start()
        try:
            assert process.stdin is not None and process.stdout is not None
            analyzer = Analyzer(process.stdin, process.stdout)
            analyzer.request(
                "initialize", {"processId": None, "rootUri": app.as_uri(), "capabilities": {}}
            )
            analyzer.send({"method": "initialized", "params": {}})
            evidence = [one_type(analyzer, app, item, definitions) for item in type_subjects()]
            analyzer.request("shutdown", None)
            analyzer.send({"method": "exit"})
            if process.wait(timeout=10) != 0 or len(evidence) != 10:
                raise ValueError("Dart analyzer did not certify all ten Compass type subjects")
            return evidence
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()


def build(output: Path, flutter: Path, source_repo: Path | None) -> None:
    pins = json.loads((PINS / "toolchain.json").read_text())
    lockfile = PINS / "pubspec.lock"
    with tempfile.TemporaryDirectory(prefix="archkeel-compass-") as work:
        temporary = Path(work)
        env = dict(os.environ)
        env.pop("PUB_HOSTED_URL", None)
        env.update(
            PUB_CACHE=str(temporary / "pub-cache"),
            FLUTTER_SUPPRESS_ANALYTICS="true",
            DART_SUPPRESS_ANALYTICS="true",
            CI="true",
        )
        machine = json.loads(
            call([str(flutter), "--version", "--machine"], temporary, env, capture=True)
        )
        versions = {key: machine.get(key) for key in VERSIONS}
        if versions != {key: pins[key] for key in VERSIONS}:
            raise ValueError(f"Compass build needs Flutter {pins['frameworkVersion']}: {versions}")
        workspace, commit = stage_source(temporary, env, source_repo)
        app = workspace / APP
        shutil.copyfile(lockfile, workspace / "pubspec.lock")
        call([str(flutter), "pub", "get", "--enforce-lockfile"], app, env)
        if sha256(workspace / "pubspec.lock") != sha256(lockfile):
            raise ValueError("Flutter changed the pinned workspace lockfile")
        roots = package_roots(workspace)
        git_packages = {
            name: git_package_digest(roots[name], env) for name in pins["git_archive_sha256"]
        }
        if git_packages != pins["git_archive_sha256"]:
            raise ValueError("Git package source differs from its SHA-256 pin")
        web = output / "web"
        call([str(flutter), "build", "web", "--no-pub", "--output", str(web)], app, env)
        artifacts = ["index.html", "main.dart.js", "assets/NOTICES"]
        result = {
            "source_commit": commit,
            "flutter": versions,
            "workspace_lock_sha256": sha256(lockfile),
            "git_archive_sha256": git_packages,
            "web_sha256": {entry: sha256(web / entry) for entry in artifacts},
            "dart_analyzer_types": prove_types(flutter, app, roots, env),
        }
        (output / "build-evidence.json").write_text(json.dumps(result, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--flutter", default="flutter")
    parser.add_argument("--source-repo", type=Path, help="use an existing Git repository read-only")
    options = parser.parse_args()
    flutter = shutil.which(options.flutter)
    if flutter is None:
        parser.error(f"Flutter SDK not found: {options.flutter}")
    output = options.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_repo = options.source_repo.resolve() if options.source_repo is not None else None
    build(output, Path(flutter).resolve(), source_repo)
    print(output / "build-evidence.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
