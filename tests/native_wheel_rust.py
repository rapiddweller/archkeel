# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the check of the Rust binary of a platform wheel.

Consumer: `test_collector_native_wheel.py`. It runs the bundled Rust collector on a small crate.
The wheel does not carry the core yet, so the installed `archkeel validate` on the same crate must
refuse with the typed `core_binary_not_found` and exit 2 (AD-432). It must never print a verdict.
"""

from __future__ import annotations

import json
import subprocess
import zlib
from pathlib import Path


def check_rust_binary(tmp_path: Path, python: Path, binary: str, version: str) -> None:
    root = tmp_path / "rust-repository"
    (root / "crates/src").mkdir(parents=True)
    (root / "crates/Cargo.toml").write_text('[package]\nname = "demo"\nversion = "0.0.0"\n')
    (root / "crates/src/lib.rs").write_text('use std::fs;\npub fn f() { fs::read("x"); }\n')
    request = {
        "protocol_version": "8.0.0",
        "snapshot": {"root": str(root), "git_head": "a" * 40, "dirty": False},
        "scope": {"roots": ["crates"], "namespace": "shop"},
        "resolver": {"language": "rust"},
    }
    reply = subprocess.run([binary], input=json.dumps(request).encode(), capture_output=True)
    assert reply.returncode == 0, reply.stderr
    facts = json.loads(zlib.decompress(reply.stdout))["facts"]
    assert facts["adapter"] == {
        "name": "archkeel-rust-imports",
        "version": version,
        "code_digest": facts["adapter"]["code_digest"],
    }
    assert facts["coverage"]["selected_files"] == ["crates/Cargo.toml", "crates/src/lib.rs"]
    # The Rust binary has no test-only mode (AD-323 keeps `dump` out of the TypeScript binary).
    dumped = subprocess.run([binary, "--dump"], input=b"", capture_output=True)
    assert dumped.returncode != 0 and dumped.stdout == b""
    (root / "architecture-contract.json").write_text(
        '{"schema_version": "2.1.0", "components": [], "rules": []}\n'
    )
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "rust"\nroots = ["crates"]\nnamespace = "shop"\n'
        'contract = "architecture-contract.json"\n'
    )
    for command in ("validate", "report"):
        host = subprocess.run(
            [str(python), "-m", "archkeel.cli", command, "--root", str(root), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert host.returncode == 2, host.stdout + host.stderr
        result = json.loads(host.stdout)
        assert set(result) == {"status", "exit_code", "refusal"}, result
        assert result["status"] == "UNKNOWN" and result["exit_code"] == 2, result
        assert result["refusal"]["kind"] == "core_binary_not_found", result
