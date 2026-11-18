# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A tsconfig alias supplies a compiler target. The runtime needs the bundler premise (#828)."""

import hashlib
import json
from pathlib import Path

import pytest
from test_collector_false_pass_sources import BASE
from test_collector_false_pass_ts_preload import _validate


@pytest.mark.parametrize(
    ("resolution", "opt_in", "paths", "generated", "held"),
    [
        ("bundler", False, True, False, True),
        ("bundler", True, True, False, False),
        ("node", True, True, False, True),
        ("bundler", True, False, False, True),
        ("bundler", True, True, True, False),
        ("bundler", False, True, True, True),
    ],
    ids=["default", "opt-in", "incompatible", "base-url-only", "bundled-copy", "default-copy"],
)
def test_alias_runtime_premise(
    tmp_path: Path,
    release_core: Path,
    resolution: str,
    opt_in: bool,
    paths: bool,
    generated: bool,
    held: bool,
) -> None:
    options = {"module": "esnext", "moduleResolution": resolution, "baseUrl": "./src"}
    specifier = "@b/b" if paths else "b/b"
    compiler = {**options, "paths": {"@b/*": ["b/*"]}} if paths else options
    config = BASE["archkeel.toml"] + ("bundler = true\n" if opt_in else "")
    source = f'import {{hidden}} from "{specifier}";\nhidden();\n'
    copies = {}
    if generated:
        digest = hashlib.sha256(source.encode()).hexdigest()
        copies = {
            "dist/a.runtime.js": f"// Generated from ../src/a/a.ts; source-sha256={digest}\n"
            "// Owner: tools/gen.py. Edit the source.\n// Check: tools/check.py\n",
            "tools/gen.py": "pass\n",
            "tools/check.py": "pass\n",
        }
    frame = _validate(
        tmp_path,
        release_core,
        {
            "tsconfig.json": json.dumps({"compilerOptions": compiler, "include": ["src"]}),
            "archkeel.toml": config,
            "src/a/a.ts": source,
            **copies,
        },
    )["frame"]
    assert frame["rules"]["REQUIRES"][1] == "FAIL"
    assert frame["rules"]["ASSIGNMENT"][1] == ("UNKNOWN" if held else "PASS")
    reasons = [gap["reason"] for gap in frame["collection_gaps"]]
    assert (f"Local alias runtime conditions are not proven: {specifier}" in reasons) == held
    active = opt_in and resolution == "bundler"
    assert ("the bundler's aliases match tsconfig paths" in frame["premise"]) == active
    assert "the runtime supplies any host global" in frame["premise"]
    assert ("a stated generated copy" in frame["premise"]) == generated
