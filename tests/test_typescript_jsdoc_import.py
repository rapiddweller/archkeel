# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Only a JSDoc type or an `@import` tag in a JavaScript file is a JSDoc import (#744).

Each expected value agrees with tsc 5.9.3: the import either pulls the module into the program
or not. A case where the reader keeps the gap although tsc does not read it is marked.
"""

import json

import pytest
from native_typescript import collect

from archkeel.ir.facts_validation import validate_source_facts
from archkeel.ir.protocol import CollectionRequest, SnapshotInput, SourceScope, TypeScriptSettings

GAP = "JSDoc import is not observed"
TYPE = "import('./a').A"


def _reasons(tmp_path, files: dict[str, str], compiler: dict[str, object]) -> list[str]:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    options = {"target": "ES2022", "strict": True, **compiler}
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": options, "include": ["src"]})
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("src",), "app"),
            TypeScriptSettings(),
        )
    )
    validate_source_facts(facts)
    return [gap.data.get("reason", "") for gap in facts.coverage.gaps]


@pytest.mark.parametrize(
    "comment",
    [
        "/**\n * After a deploy the dynamic import() fails.\n */",
        "/** call import(x) later */",
        f"/** @type {{{TYPE}}} */",
    ],
)
def test_the_collector_reports_no_jsdoc_import_in_a_typescript_file(tmp_path, comment) -> None:
    files = {"src/a.ts": "export type A = 1;\n", "src/b.ts": f"{comment}\nexport const k = 1;\n"}
    assert GAP not in _reasons(tmp_path, files, {})


@pytest.mark.parametrize(
    ("comment", "gap"),
    [
        ("/**\n * After a deploy the dynamic import() fails.\n */", False),
        (f"/** @type {{{TYPE}}} */", True),
        ("/** @import {A} from './a' */", True),
        (f"/** @template [T={TYPE}] */", True),
        ("/** @template [T=number] the dynamic import('./a') fails */", False),
    ],
)
def test_the_collector_reports_a_jsdoc_type_import_in_a_javascript_file(
    tmp_path, comment: str, gap: bool
) -> None:
    files = {"src/a.ts": "export type A = 1;\n", "src/b.js": f"{comment}\nexport const k = 1;\n"}
    assert (GAP in _reasons(tmp_path, files, {"allowJs": True})) is gap
