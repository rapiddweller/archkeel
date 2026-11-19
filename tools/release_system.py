# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check the bound system frame of the candidate wheel before the final 5.0 release."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

SYSTEM = "docs/architecture/architecture-system.json"
MEMBER = "archkeel/_native/archkeel-core"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def loads(text: str) -> Any:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=unique)


def check(result: object, root: Path, document: str, wheel: Path, commit: str) -> list[str]:
    """Read decisions, not a badge or exit code. A malformed or unbound frame is refused."""
    try:
        require(isinstance(result, dict) and "refusal" not in result, "no accepted frame")
        if not isinstance(result, dict):
            raise ValueError("no result object")
        frame = result["frame"]
        require(frame["engine"].startswith("archkeel-core "), "wrong engine")
        core = Path(result["core"]["path"])
        require(core.name == "archkeel-core" and core.parent.name == "_native", "wrong core path")
        with zipfile.ZipFile(wheel) as archive:
            require(core.read_bytes() == archive.read(MEMBER), "core differs from wheel")
        collect = frame["self_test"]["collect"]
        snapshot = collect["request"]["snapshot"]
        require(
            snapshot == {"root": str(root), "git_head": commit, "dirty": False}, "snapshot differs"
        )
        files = collect["contract_files"]

        def bound(name: str) -> bytes:
            path = root / name
            require(
                path.resolve(strict=True).is_relative_to(root) and path.is_file(), "unsafe file"
            )
            data = path.read_bytes()
            require(files[name] == hashlib.sha256(data).hexdigest(), f"unbound file: {name}")
            return data

        system = loads(bound(document).decode())
        require(system["kind"] == "system" and not system["rules"], "unsupported system contract")
        require(frame["contract_digest"] == files[document], "system digest differs")
        actual = frame["system"]
        require(actual["document"] == document, "wrong system document")
        parts = actual["parts"]
        require(len(parts) == len(system["parts"]), "system parts differ")
        expected: dict[str, str] = {}
        for declared, part in zip(system["parts"], parts, strict=True):
            require(
                (part["id"], part["config"]) == (declared["id"], declared["config"]), "wrong part"
            )
            config = tomllib.loads((root / declared["config"]).read_text())
            contract = loads(bound(config["scan"]["contract"]).decode())
            require(
                not any(component.get("inside") for component in contract["components"]),
                "inside contracts need explicit rule identity support",
            )
            rules = contract["rules"]
            ids = [rule["id"] for rule in rules]
            require(
                len(ids) == len(set(ids)) and not (set(ids) & expected.keys()),
                "duplicate contract rule",
            )
            require(
                len(part["rules"]) == len(ids) and set(part["rules"]) == set(ids),
                f"part {part['id']} has missing, repeated or foreign rules",
            )
            expected.update({rule["id"]: rule["kind"] for rule in rules})
        rows = frame["rules"]
        require(
            bool(expected) and set(rows) == set(expected), "system rule IDs differ from contracts"
        )
        failed = [name for name, kind in expected.items() if rows[name] != [kind, "PASS"]]
        require(not failed, f"rules not PASS: {failed}")
        return []
    except (AssertionError, KeyError, TypeError, ValueError, OSError, zipfile.BadZipFile) as error:
        return [str(error) or f"invalid system evidence: {type(error).__name__}"]


def main(wheel: Path, commit: str) -> int:
    root = Path.cwd().resolve()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if head != commit:
        print("release refused: checkout commit differs from release commit", file=sys.stderr)
        return 2
    print(
        f"release commit: {commit}; wheel sha256: {hashlib.sha256(wheel.read_bytes()).hexdigest()}"
    )
    command = [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        "--with",
        str(wheel.resolve()),
        "python",
        "-m",
        "archkeel.cli",
        "validate",
        "--root",
        str(root),
        "--config",
        SYSTEM,
        "--json",
    ]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    try:
        with tempfile.TemporaryDirectory() as directory:
            run = subprocess.run(command, cwd=directory, env=env, capture_output=True, text=True)
        result = loads(run.stdout)
        evidence = root / "test-artifacts" / "release-system.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(run.stdout)
        if isinstance(result, dict) and isinstance(result.get("frame"), dict):
            frame = result["frame"]
            print(
                json.dumps(
                    {
                        key: frame.get(key)
                        for key in ("premise", "premises", "assuming", "assumed", "door_reach")
                    }
                )
            )
        problems = check(result, root, SYSTEM, wheel, commit)
    except (OSError, ValueError) as error:
        problems = [str(error)]
    for problem in problems:
        print(f"release refused: {problem}", file=sys.stderr)
    return 2 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python -m tools.release_system WHEEL COMMIT")
    sys.exit(main(Path(sys.argv[1]), sys.argv[2]))
