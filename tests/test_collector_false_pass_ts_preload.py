# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A preload that the repository names in a data file holds the rule (#1750, AD-830).

A tool loads an installed package before the code of the scan, with no import of the scan:
`node --require preload`, `NODE_OPTIONS`, a test setup. The plant of #1750: `preload` installs the
function `hidden` of component `b` as `globalThis.open`, and component `a` calls `window.open()`.
Node runs the function of `b` (`node --require preload src/a/a.js`). The rule must not PASS, and the
gap names the write. A preload that patches the module loader can redirect any import, so it holds
every rule. A preload name that names no installed package is a gap with its name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only

WRITER = 'globalThis.open = require("../../src/b/b").hidden;\n'
PATCH = (
    "const Module = require('module');\nconst load = Module._load;\n"
    "Module._load = function (request, ...rest) { return load(request, ...rest); };\n"
)
QUIET_CODE = "class Store { constructor() { this._cache = new Map(); } }\nmodule.exports = Store;\n"


def _preload(code: str, name: str = "preload") -> dict[str, str]:
    return {
        f"node_modules/{name}/package.json": f'{{"name":"{name}","main":"index.js"}}',
        f"node_modules/{name}/index.js": code,
    }


def _scripts(command: str) -> dict[str, str]:
    return {"package.json": f'{{"name":"app","scripts":{{"start":"{command}"}}}}'}


# Each place that names the preload, with the write of `preload` (the plant of #1750).
NAMED: dict[str, dict[str, str]] = {
    "require-flag": _scripts("node --require preload src/a/a.js"),
    "short-flag": _scripts("node -r preload src/a/a.js"),
    "import-flag": _scripts("node --import=preload src/a/a.js"),
    "loader-flag": _scripts("node --experimental-loader preload src/a/a.js"),
    "script-node-options": _scripts("NODE_OPTIONS='--require preload' node src/a/a.js"),
    "npmrc": {".npmrc": "node-options=--require preload\n"},
    "env": {".env": "NODE_OPTIONS=--require preload\n"},
    "jest-setup": {"package.json": '{"name":"app","jest":{"setupFiles":["preload"]}}'},
    "jest-global-setup": {"jest.config.json": '{"globalSetup":"preload"}'},
    "mocha-require": {".mocharc.yml": "require:\n  - preload\n"},
    "vitest-setup": {"vitest.config.ts": "export default { test: { setupFiles: ['preload'] } };\n"},
}

# A preload that patches the module loader holds every rule; a name with no package is a gap.
HELD: dict[str, tuple[dict[str, str], str]] = {
    "project-source-reach": (
        {
            **_scripts("node -r preload src/a/a.js"),
            **_preload('require("../../src/b/b");\n'),
        },
        "Preload preload named in package.json:1 has an incomplete closure",
    ),
    "unknown-loader": (
        {
            **_scripts("node -r preload src/a/a.js"),
            **_preload("const target = process.env.PRELOAD; require(target);\n"),
        },
        "Preload preload named in package.json:1 has an incomplete closure",
    ),
    "module-load": (
        {**_scripts("node -r preload src/a/a.js"), **_preload(PATCH)},
        "patches the module loader at node_modules/preload/index.js:2",
    ),
    "require-cache": (
        {
            **_scripts("node -r preload src/a/a.js"),
            **_preload("require.cache[require.resolve('x')] = { exports: {} };\n"),
        },
        "patches the module loader at node_modules/preload/index.js:1",
    ),
    "missing": (
        _scripts("node -r missing-preload src/a/a.js"),
        "Preload missing-preload named in package.json:1 is no installed package",
    ),
    "malformed-config": (
        {"package.json": '{"scripts":'},
        "Preload configuration package.json is malformed",
    ),
}

# A preload that writes no global and patches no loader keeps the proof.
QUIET: dict[str, dict[str, str]] = {
    "harmless": {**_scripts("node -r preload src/a/a.js"), **_preload("exports.ready = true;\n")},
    "own-cache": {**_scripts("node -r preload src/a/a.js"), **_preload(QUIET_CODE)},
    "builtin": _scripts("node --require node:util src/a/a.js"),
}


def _validate(tmp_path: Path, release_core: Path, extra: dict[str, str]) -> dict[str, Any]:
    root = tmp_path / "repo"
    files = {
        **BASE,
        "src/a/a.ts": "window.open();\n",
        "src/b/b.ts": "export function hidden() {}\n",
        **extra,
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    commit_tree(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        return run("validate", "--root", str(root))[1]


@pytest.mark.parametrize("name", sorted(NAMED))
def test_a_named_preload_that_replaces_a_global_holds_the_rule(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    document = _validate(tmp_path, release_core, {**NAMED[name], **_preload(WRITER)})
    frame = document["frame"]
    assert frame["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, (name, frame["rules"])
    places = {
        f"{place['path']}:{place['line']}"
        for gap in frame["collection_gaps"]
        if gap["reason"] == "Script global open is replaced by a file outside the scan roots"
        for evidence in gap["evidence"]
        if (place := frame["locations"].get(evidence))
    }
    assert "node_modules/preload/index.js:1" in places, (name, frame["collection_gaps"])


@pytest.mark.parametrize("name", sorted(HELD))
def test_a_loader_patch_or_an_unknown_preload_holds_every_rule(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    files, reason = HELD[name]
    frame = _validate(tmp_path, release_core, files)["frame"]
    assert frame["rules"]["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, (name, frame["rules"])
    assert frame["rules"]["ASSIGNMENT"][1] in {"FAIL", "UNKNOWN"}, (name, frame["rules"])
    reasons = [gap["reason"] for gap in frame["collection_gaps"]]
    assert any(reason in text for text in reasons), (name, reasons)


@pytest.mark.parametrize("name", sorted(QUIET))
def test_a_quiet_preload_keeps_the_pass(tmp_path: Path, release_core: Path, name: str) -> None:
    frame = _validate(tmp_path, release_core, QUIET[name])["frame"]
    assert frame["rules"]["REQUIRES"][1] == "PASS", (name, frame["collection_gaps"])
