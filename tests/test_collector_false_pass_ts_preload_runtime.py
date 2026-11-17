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
    ("mode", "conditions", "runtime_path", "runtime_code"),
    [
        (
            "require",
            '"types":"./types.ts","require":"./runtime.cjs"',
            "runtime.cjs",
            PATCH + "console.log('RUNTIME_REQUIRE');\n",
        ),
        (
            "import",
            '"types":"./types.ts","import":"./runtime.mjs"',
            "runtime.mjs",
            "import Module from 'node:module';\n"
            "const old = Module._load;\n"
            "Module._load = function (...args) { console.log('RUNTIME_IMPORT'); "
            "return Reflect.apply(old, this, args); };\n"
            "console.log('RUNTIME_IMPORT');\n",
        ),
        (
            "require",
            '"types":"./types.ts","default":"./runtime.cjs"',
            "runtime.cjs",
            PATCH + "console.log('RUNTIME_DEFAULT');\n",
        ),
        (
            "require",
            '"require":"./runtime.cjs","types":"./types.ts"',
            "runtime.cjs",
            PATCH + "console.log('RUNTIME_ORDER');\n",
        ),
    ],
    ids=(
        "require-skips-types",
        "import-skips-types",
        "default-skips-types",
        "require-before-types",
    ),
)
def test_exports_conditions_select_the_node_runtime_target(
    tmp_path: Path,
    release_core: Path,
    mode: str,
    conditions: str,
    runtime_path: str,
    runtime_code: str,
) -> None:
    flag = "--require" if mode == "require" else "--import"
    marker = runtime_code.split("console.log('", 1)[1].split("'", 1)[0]
    extra = {
        **_scripts(f"node {flag} hook src/a/a.js"),
        "node_modules/hook/package.json": ('{"name":"hook","exports":{".":{' + conditions + "}}}"),
        "node_modules/hook/types.ts": "export const ready = true;\n",
        f"node_modules/hook/{runtime_path}": runtime_code,
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = _node(tmp_path / "repo", flag, "hook", "-e", "console.log('NODE_MAIN')")
    assert result.returncode == 0, result.stderr
    assert marker in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, frame["rules"]
    assert any("patches the module loader" in gap["reason"] for gap in frame["collection_gaps"])


def test_a_runtime_typescript_export_is_unknown_without_a_node_version(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        **_scripts("node --require hook src/a/a.js"),
        "node_modules/hook/package.json": (
            '{"name":"hook","exports":{".":{"types":"./types.ts","require":"./runtime.ts"}}}'
        ),
        "node_modules/hook/types.ts": "export const ready = true;\n",
        "node_modules/hook/runtime.ts": "console.log('RUNTIME_TS');\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]
    assert any("Node runtime target" in gap["reason"] for gap in frame["collection_gaps"]), frame[
        "collection_gaps"
    ]
    result = _node(tmp_path / "repo", "--require", "hook", "-e", "console.log('NODE_MAIN')")
    if result.returncode == 0:
        assert "RUNTIME_TS" in result.stdout, result.stdout


def test_transitive_exports_ignore_the_types_condition(tmp_path: Path, release_core: Path) -> None:
    extra = {
        **_scripts("node --require hook src/a/a.js"),
        "node_modules/hook/package.json": '{"name":"hook","main":"index.js"}',
        "node_modules/hook/index.js": "require('dep');\n",
        "node_modules/dep/package.json": (
            '{"name":"dep","exports":{".":{"types":"./types.ts","require":"./runtime.cjs"}}}'
        ),
        "node_modules/dep/types.ts": "export const ready = true;\n",
        "node_modules/dep/runtime.cjs": PATCH + "console.log('TRANSITIVE_RUNTIME');\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = _node(tmp_path / "repo", "--require", "hook", "-e", "console.log('NODE_MAIN')")
    assert result.returncode == 0, result.stderr
    assert "TRANSITIVE_RUNTIME" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, frame["rules"]
    assert any("patches the module loader" in gap["reason"] for gap in frame["collection_gaps"])


def test_transitive_typescript_runtime_target_stays_unknown(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        **_scripts("node --require hook src/a/a.js"),
        "node_modules/hook/package.json": '{"name":"hook","main":"index.js"}',
        "node_modules/hook/index.js": "require('dep');\n",
        "node_modules/dep/package.json": (
            '{"name":"dep","exports":{".":{"types":"./types.ts","require":"./runtime.ts"}}}'
        ),
        "node_modules/dep/types.ts": "export const ready = true;\n",
        "node_modules/dep/runtime.ts": "console.log('TRANSITIVE_TS');\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]
    assert any("Node runtime target" in gap["reason"] for gap in frame["collection_gaps"]), frame[
        "collection_gaps"
    ]
    result = _node(tmp_path / "repo", "--require", "hook", "-e", "console.log('NODE_MAIN')")
    if result.returncode == 0:
        assert "TRANSITIVE_TS" in result.stdout, result.stdout


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
