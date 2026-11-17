# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An installed package that imports project source gives no PASS (#1529, AD-798).

Consumer: `archkeel validate` on a TypeScript project, through the release core. Module `a`
imports an installed package, and the code of that package imports `src/b/t.ts`. So `a` depends on
`b`, which the contract forbids. The rule must give FAIL or UNKNOWN. Node 26 loads each runtime
plant and reaches the file of `b`. The group `PRECISION` must keep its PASS: a package that imports
only a builtin or another package, and an installed package that the scan does not import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only

USE = "import { hidden } from 'local';\nexport const a = hidden;\n"
MANIFEST = '{"name":"local","main":"index.js"}'

FORMS: dict[str, dict[str, str]] = {
    # The audit plant of #1529: a package below a scan root.
    "below-a-root": {
        "src/a/node_modules/local/package.json": '{"name":"local","main":"index.ts"}',
        "src/a/node_modules/local/index.ts": 'import "../../../b/t";\nexport const hidden = 1;\n',
    },
    "below-a-root-with-owner": {
        "src/a/package.json": '{"name":"owner","version":"1.0.0"}',
        "src/a/node_modules/local/package.json": '{"name":"local","main":"index.ts"}',
        "src/a/node_modules/local/index.ts": 'import "../../../b/t";\nexport const hidden = 1;\n',
    },
    "repository-root": {
        "node_modules/local/package.json": MANIFEST,
        "node_modules/local/index.js": 'import "../../src/b/t";\nexport const hidden = 1;\n',
    },
    "require": {
        "node_modules/local/package.json": MANIFEST,
        "node_modules/local/index.js": 'require("../../src/b/t");\nexports.hidden = 1;\n',
    },
    "through-another-package": {
        "node_modules/local/package.json": MANIFEST,
        "node_modules/local/index.js": 'import "inner";\nexport const hidden = 1;\n',
        "node_modules/inner/package.json": '{"name":"inner","main":"index.js"}',
        "node_modules/inner/index.js": 'import "../../src/b/t";\n',
    },
    "type-only": {
        "node_modules/local/package.json": '{"name":"local","types":"index.d.ts"}',
        "node_modules/local/index.d.ts": (
            'import type { T } from "../../src/b/t";\nexport declare const hidden: T;\n'
        ),
    },
    "path-directive": {
        "node_modules/local/package.json": '{"name":"local","types":"index.d.ts"}',
        "node_modules/local/index.d.ts": (
            '/// <reference path="../../src/b/t.ts" />\nexport declare const hidden: number;\n'
        ),
    },
    # The resolver does not decide `typesVersions`: each file of `inner` is read.
    "types-versions": {
        "node_modules/local/package.json": '{"name":"local","types":"index.d.ts"}',
        "node_modules/local/index.d.ts": (
            'import type { I } from "inner";\nexport declare const hidden: I;\n'
        ),
        "node_modules/inner/package.json": (
            '{"name":"inner","types":"index.d.ts","typesVersions":{"*":{"*":["ts4/*"]}}}'
        ),
        "node_modules/inner/index.d.ts": "export type I = number;\n",
        "node_modules/inner/ts4/index.d.ts": (
            'import type { T } from "../../../src/b/t";\nexport type I = T;\n'
        ),
    },
}

PRECISION: dict[str, dict[str, str]] = {
    # `@types/react` and `next` name their own files with a path directive.
    "own-path-directive": {
        "node_modules/local/package.json": '{"name":"local","types":"index.d.ts"}',
        "node_modules/local/index.d.ts": (
            '/// <reference path="global.d.ts" />\nexport declare const hidden: number;\n'
        ),
        "node_modules/local/global.d.ts": "declare var fromLocal: number;\n",
    },
    "builtin-and-package": {
        "node_modules/local/package.json": MANIFEST,
        "node_modules/local/index.js": (
            'import "node:fs";\nimport "inner";\nexport const hidden = 1;\n'
        ),
        "node_modules/inner/package.json": '{"name":"inner","main":"index.js"}',
        "node_modules/inner/index.js": "export const inner = 1;\n",
    },
    "not-imported": {
        "node_modules/local/package.json": MANIFEST,
        "node_modules/local/index.js": "export const hidden = 1;\n",
        "node_modules/other/package.json": '{"name":"other","main":"index.js"}',
        "node_modules/other/index.js": 'import "../../src/b/t";\n',
    },
}


def _verdict(tmp_path: Path, release_core: Path, files: dict[str, str]) -> dict[str, Any]:
    root = tmp_path / "repo"
    for rel, text in {**BASE, "src/a/a.ts": USE, **files}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    commit_tree(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        return run("validate", "--root", str(root))[1]


@pytest.mark.parametrize("name", sorted(FORMS))
def test_an_installed_package_that_reaches_project_source_holds_the_rule(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    document = _verdict(tmp_path, release_core, FORMS[name])
    rows = document["frame"]["rules"]
    assert "REQUIRES" in rows and not document.get("refusal"), document
    assert rows["REQUIRES"][1] in {"FAIL", "UNKNOWN"}, (name, document["frame"])


@pytest.mark.parametrize("name", sorted(PRECISION))
def test_an_installed_package_without_project_source_keeps_the_pass(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    document = _verdict(tmp_path, release_core, PRECISION[name])
    assert document["status"] == "PASS", (name, document["frame"])
