# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Node runtime resolution must cover preload entries and their imports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_collector_false_pass_ts_preload import PATCH, _node, _scripts, _validate


@pytest.mark.parametrize(
    ("runtime_files", "typescript_files"),
    [
        (
            {"node_modules/hook/index.js": PATCH + "console.log('runtime-patch');\n"},
            {"node_modules/hook/index.ts": "exports.ready = true;\n"},
        ),
        (
            {
                "node_modules/hook/index.js": "require('./child.js');\n",
                "node_modules/hook/child.js": PATCH + "console.log('runtime-patch');\n",
            },
            {
                "node_modules/hook/index.ts": "exports.ready = true;\n",
                "node_modules/hook/child.ts": "exports.ready = true;\n",
            },
        ),
    ],
    ids=("entry-runtime-main", "transitive-runtime-import"),
)
def test_preload_closure_follows_node_runtime_files(
    tmp_path: Path,
    release_core: Path,
    runtime_files: dict[str, str],
    typescript_files: dict[str, str],
) -> None:
    extra = {
        **_scripts("node --require hook src/a/a.js"),
        "node_modules/hook/package.json": '{"name":"hook","main":"index.js"}',
        **runtime_files,
        **typescript_files,
    }
    frame: dict[str, Any] = _validate(tmp_path, release_core, extra)["frame"]
    result = _node(tmp_path / "repo", "--require", "hook", "-e", "console.log('node-loaded')")
    assert result.returncode == 0, result.stderr
    assert "runtime-patch" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, frame["rules"]
    assert any("patches the module loader" in gap["reason"] for gap in frame["collection_gaps"])
