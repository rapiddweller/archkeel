# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-366: the Rust contract crate assembles each inside-contract tree as Python does.

The corpus is each root contract of the repository that mounts an inside contract, the hostile
trees of `rust_contract_tree_cases` and generated trees. For each tree the accept or reject
decision, each issue (pointer, parent ID, path, kind and reason) and, for an accepted tree, each
mount, the provenance paths, both tree digests and the canonical bytes of each scoped contract and
of the comparison contract must be equal.

Rust is stricter than Python in six named cases, and only there (AD-366, `docs/known-limits.md`):

- `Unmounted`: bytes that no mount reads.
- `Duplicate`: two inputs with one path.
- `Unsafe`: an input path or identity that is not a repository path, such as a link out of the
  repository.
- `contract_duplicate_key`: a JSON object with one key two times (AD-364).
- `too_deep`: a mount deeper than 900 levels; Python stops near 984 with no verdict.
- `linked`: an input whose identity differs from its reference, a symbolic link; Python refuses
  a link to a mounted file as a duplicate mount and accepts a link to an unmounted file.

`STRICTER` names the hostile trees of the last four; the first three have their own tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock
from rust_contract_tree_cases import (
    LINKS,
    Tree,
    generated_trees,
    hostile_trees,
    identity,
    repository_trees,
)

from archkeel.ir.codec import (
    ContractInputError,
    ContractVersionError,
    contract_bytes,
    load_inside_contract_tree,
    parse_contract,
)
from archkeel.ir.codec_wire import decode_json

NATIVE = Path(__file__).parents[1] / "native"
FIXED = {
    "unsafe repository path": "unsafe_path",
    "generated inside parent ID collision": "parent_id_collision",
    "reference cycle": "cycle",
    "duplicate mount": "duplicate_mount",
    "missing": "missing",
}
PREFIXED = {
    "unsupported non-empty declarations: ": "unsupported_declarations",
    "generated declaration ID collision: ": "declaration_id_collision",
    "duplicate module target path ": "duplicate_module_target",
}
# The cases where Rust is stricter than Python, with the Rust result that the case must give.
STRICTER = {
    "inside with duplicate key": "contract_duplicate_key",
    "chain one level deeper": "too_deep",
    "link to a mounted file": "linked",
    "link to an unmounted file": "linked",
    "link out of the repository": "unsafe",
}


def _probe() -> Path:
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native contract tree parity test.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    (NATIVE / "target").mkdir(exist_ok=True)
    command = [
        cargo,
        "build",
        "--locked",
        "-p",
        "archkeel-contract",
        "--example",
        "contract_tree_dump",
    ]
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        built = subprocess.run(command, cwd=NATIVE, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    name = "contract_tree_dump" + (".exe" if os.name == "nt" else "")
    return NATIVE / "target/debug/examples" / name


def _rust(probe: Path, trees: list[tuple[str, dict[str, bytes]]]) -> list[dict[str, Any]]:
    lines = []
    for root_path, files in trees:
        sources = [[root_path, root_path, files[root_path].hex()]]
        sources += [
            [path, LINKS.get(path, path), data.hex()]
            for path, data in files.items()
            if path != root_path
        ]
        lines.append(json.dumps(sources))
    text = "".join(f"{line}\n" for line in lines)
    run = subprocess.run([probe], input=text.encode(), capture_output=True, check=True)
    return [json.loads(line) for line in run.stdout.decode().splitlines()]


def _parse_kind(raw: bytes) -> str:
    try:
        parse_contract(decode_json(raw))
    except ContractInputError:
        return "input"
    except ContractVersionError:
        return "version"
    except ValueError:
        return "invalid"
    return "accept"


def _issue_kind(reason: str, error: object, raw: bytes | None) -> str:
    if reason in FIXED:
        return FIXED[reason]
    for prefix, kind in PREFIXED.items():
        if reason.startswith(prefix):
            return kind
    if error is not None:
        return "contract_input"
    return f"contract_{_parse_kind(raw or b'')}"


def _python(root_path: str, files: dict[str, bytes]) -> tuple[dict[str, Any], set[str]]:
    """The Python result, and the paths that Python reads."""
    root_bytes = files[root_path]
    kind = _parse_kind(root_bytes)
    if kind != "accept":
        return {"kind": "root", "error": kind}, set()
    read_paths = {root_path}

    def read(reference: str) -> tuple[bytes, str]:
        key = identity(reference)
        if key is None or key not in files:
            raise ValueError("missing")
        resolved = LINKS.get(key, key)
        if identity(resolved) is None:
            raise ValueError("missing")
        read_paths.add(key)
        return files[key], resolved

    root = parse_contract(decode_json(root_bytes))
    digest = hashlib.sha256(root_bytes).hexdigest()
    try:
        tree = load_inside_contract_tree(root_path, root, digest, root_path, read)
    except ValueError:
        return {"kind": "unsafe_root"}, set()
    if tree.issues:
        issues = []
        for issue in tree.issues:
            key = identity(issue.path)
            raw = files.get(key) if key is not None else None
            kind = _issue_kind(issue.reason, issue.input_error, raw)
            text = None if kind.startswith("contract_") or kind == "missing" else issue.reason
            issues.append(
                {
                    "pointer": issue.pointer,
                    "parent_id": issue.parent_id,
                    "path": issue.path,
                    "kind": kind,
                    "reason": text,
                }
            )
        return {"kind": "issues", "issues": issues}, read_paths
    mounts = [
        {
            "owner_id": mount.owner_id,
            "parent_id": mount.parent_id,
            "parent": mount.parent.id,
            "pointer": mount.pointer,
            "path": mount.path,
            "identity": mount.identity,
            "digest": mount.digest,
            "canonical_digest": mount.canonical_digest,
            "canonical": contract_bytes(mount.contract).decode(),
        }
        for mount in tree.mounts
    ]
    try:
        comparison: str | None = contract_bytes(tree.comparison_contract).decode()
    except ValueError:
        comparison = None  # Python writes no bytes for a mix of versions; the ids still count.
    return {
        "kind": "accept",
        "mounts": mounts,
        "components": [item.id for item in tree.comparison_contract.components],
        "rules": [item.id for item in tree.comparison_contract.rules],
        "paths": list(tree.paths),
        "digest": tree.digest,
        "comparison_digest": tree.comparison_digest,
        "comparison": comparison,
    }, read_paths


def _comparable(result: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """Rust gives no reason for a contract error or a missing file: the texts differ. Python
    writes no comparison bytes when the root version cannot hold a rule of an inside."""
    if result.get("kind") == "accept" and expected.get("comparison", "") is None:
        return {**result, "comparison": None}
    if result.get("kind") != "issues":
        return result
    issues = [
        {
            **item,
            "reason": None
            if item["kind"].startswith("contract_") or item["kind"] == "missing"
            else item["reason"],
        }
        for item in result["issues"]
    ]
    return {**result, "issues": issues}


def _corpus() -> list[Tree]:
    return [*repository_trees(), *hostile_trees(), *generated_trees()]


def test_the_rust_tree_is_the_python_tree() -> None:
    probe = _probe()
    corpus = _corpus()
    python = [_python(root_path, files) for _, root_path, files in corpus]
    rust = _rust(probe, [(root_path, files) for _, root_path, files in corpus])
    trimmed = []
    tally_stricter: list[str] = []
    for (name, root_path, files), (expected, read_paths), actual in zip(
        corpus, python, rust, strict=True
    ):
        if name in STRICTER:
            kinds = [item["kind"] for item in actual.get("issues", [])]
            assert STRICTER[name] in [*kinds, actual.get("error")], (name, actual)
            tally_stricter.append(name)
            continue
        extra = sorted(set(files) - read_paths)
        if expected["kind"] == "accept" and extra:
            assert actual == {"kind": "source", "error": "unmounted", "paths": extra}, name
            kept = {path: files[path] for path in sorted(read_paths)}
            trimmed.append((name, root_path, expected, kept))
            continue
        assert _comparable(actual, expected) == expected, name
    again = _rust(probe, [(root_path, files) for _, root_path, _, files in trimmed])
    for (name, _, expected, _), actual in zip(trimmed, again, strict=True):
        assert _comparable(actual, expected) == expected, name
    assert sorted(tally_stricter) == sorted(STRICTER), tally_stricter
    decisions = [item[0]["kind"] for item in python]
    assert decisions.count("accept") >= 40, decisions
    assert decisions.count("issues") >= 60, decisions
    assert len(repository_trees()) >= 6


def test_the_repository_trees_are_accepted() -> None:
    for name, root_path, files in repository_trees():
        result, _ = _python(root_path, files)
        assert result["kind"] == "accept", (name, result)
        assert result["mounts"], name


def test_rust_rejects_two_sources_with_one_path() -> None:
    probe = _probe()
    _, root_path, files = hostile_trees()[0]
    sources = [[root_path, root_path, files[root_path].hex()]]
    sources += [[path, path, data.hex()] for path, data in files.items() if path != root_path]
    sources.append(["a/./inside.json", "a/inside.json", files["a/inside.json"].hex()])
    run = subprocess.run(
        [probe], input=f"{json.dumps(sources)}\n".encode(), capture_output=True, check=True
    )
    assert json.loads(run.stdout) == {
        "kind": "source",
        "error": "duplicate",
        "paths": ["a/inside.json"],
    }
