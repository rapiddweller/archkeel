# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-335: the check of the Rust binary of a platform wheel.

Consumer: `test_collector_native_wheel.py`. It runs the bundled Rust collector on a small crate,
and runs the installed host with its default Rust collector on the same crate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sysconfig
import zlib
from pathlib import Path

# The installed host runs the bundled Rust binary through its default collector.
HOST_RUN = """
import json
import sys

from archkeel.cli.observe import observer_for
from archkeel.ir.facts import Language
from archkeel.ir.protocol import CollectionRequest, RustSettings, SnapshotInput, SourceScope

request = CollectionRequest(
    SnapshotInput(sys.argv[1], "a" * 40, False), SourceScope(("crates",), "shop"), RustSettings()
)
facts = observer_for(Language.RUST).collector.collect(request)
print(json.dumps([type(facts).__name__, facts.adapter.name, facts.adapter.version,
                  [item.module for item in facts.files]]))
"""


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
    assert facts["coverage"]["selected_files"] == ["crates/src/lib.rs"]
    # The Rust binary has no test-only mode (AD-323 keeps `dump` out of the TypeScript binary).
    dumped = subprocess.run([binary, "--dump"], input=b"", capture_output=True)
    assert dumped.returncode != 0 and dumped.stdout == b""
    host = subprocess.run(
        [str(python), "-c", HOST_RUN, str(root)],
        env={**os.environ, "PYTHONPATH": sysconfig.get_paths()["purelib"]},
        capture_output=True,
        text=True,
        check=False,
    )
    assert host.returncode == 0, host.stderr
    assert json.loads(host.stdout) == [
        "SourceFacts",
        "archkeel-rust-imports",
        version,
        ["shop.demo"],
    ]
