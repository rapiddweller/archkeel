# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-564: a TypeScript and a Dart gap hold only the rules that read their effect.

Consumer: a user whose project has one gap that leaves the code of every module unknown. The rule
on the files (`ASSIGN`) still has its verdict; the rule that reads an import (`A-NO-B`) stays
UNKNOWN, and a violation that the scan sees stays FAIL beside the gap. A gap without an effect
holds every rule. Each tree has two components, `a` and `b`; `A-NO-B` forbids `a` to use `b`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import NamedTuple

import pytest
from corpus_support import commit_tree
from test_cli_native_python_imports import rows, verdict

GRAPH = "# Target\n\n<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n    a --> b\n```\n"
TS_CONFIG = {
    "compilerOptions": {"target": "ES2022", "module": "esnext", "moduleResolution": "bundler"},
    "include": ["src"],
}
# A computed key that can name `constructor` can write any global, so no free standard name of
# any module is proven (`Math` below is such a name).
WRITES_ANY_GLOBAL = (
    "export const call = (o: any, k: string) => o[k]();\nexport const m = Math.min(1, 2);\n"
)


# An import that no file answers: the collector writes an unresolved import and a resolution gap.
UNRESOLVED = "import { q } from './missing';\nexport const x = q;\n"


class Language(NamedTuple):
    config: str
    files: dict[str, str]
    source: tuple[str, str]
    # The import of `b` from the file of `a`.
    uses_b: str


TYPESCRIPT = Language(
    config=(
        'language = "typescript"\nroots = ["src"]\nnamespace = "app"\ntsconfig = "tsconfig.json"\n'
    ),
    files={
        "tsconfig.json": json.dumps(TS_CONFIG),
        "package.json": '{"name": "app", "private": true, "type": "module"}\n',
        "src/b/y.ts": "export const y = 1;\n",
    },
    source=("src/a/x.ts", "export const x = 1;\n"),
    uses_b="import { y } from '../b/y';\nexport const z = y;\n",
)
DART = Language(
    config='language = "dart"\nroots = ["lib"]\nnamespace = "app"\n',
    files={
        "pubspec.yaml": "name: app\nenvironment:\n  sdk: ^3.5.0\n",
        "lib/src/b/y.dart": "const y = 1;\n",
    },
    source=("lib/src/a/x.dart", "const x = 1;\n"),
    uses_b="import '../b/y.dart';\nconst z = y;\n",
)
# A workspace key makes `package:` URIs resolve in packages that the survey does not read.
WORKSPACE = "name: app\nworkspace:\n  - other\nenvironment:\n  sdk: ^3.5.0\n"


def project(root: Path, language: Language, more: dict[str, str]) -> Path:
    rule = {"rationale": "r", "provenance": ["p"], "decided_by": "architect"}
    components = [
        {
            "id": f"COMP-{label.upper()}",
            "label": label,
            "role": "component",
            "packages": [f"app.src.{label}"],
            "public": [f"app.src.{label}"],
            "responsibilities": [label],
            "forbidden_responsibilities": [],
            "provenance": ["p"],
            "requires": [{"component": "b", "rationale": "r"}] if label == "a" else [],
            "decided_by": "architect",
        }
        for label in ("a", "b")
    ]
    rules = [
        {**rule, "id": "ASSIGN", "kind": "complete_assignment", "source": "app"},
        {
            **rule,
            "id": "A-NO-B",
            "kind": "forbidden_dependency",
            "source": "app.src.a",
            "target": "app.src.b",
            "include_type_checking": True,
        },
    ]
    contract = {"schema_version": "2.2.0", "components": components, "rules": rules}
    files = {
        "archkeel.toml": f'[scan]\n{language.config}contract = "architecture-contract.json"\n',
        "architecture-contract.json": json.dumps(contract),
        "p": GRAPH,
        language.source[0]: language.source[1],
        **language.files,
        **more,
    }
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    commit_tree(root)
    return root


PLANTS = {
    "typescript clean": (TYPESCRIPT, {}, {"ASSIGN": "PASS", "A-NO-B": "PASS"}),
    "typescript gap": (
        TYPESCRIPT,
        {"src/b/y.ts": "export const y = 1;\n" + WRITES_ANY_GLOBAL},
        {"ASSIGN": "PASS", "A-NO-B": "UNKNOWN"},
    ),
    "typescript seen violation beside the gap": (
        TYPESCRIPT,
        {
            "src/a/x.ts": TYPESCRIPT.uses_b,
            "src/b/y.ts": "export const y = 1;\n" + WRITES_ANY_GLOBAL,
        },
        {"ASSIGN": "PASS", "A-NO-B": "FAIL"},
    ),
    # A resolution gap without an effect (an unresolved import) leaves the edges unknown, not the
    # files and their owners: `ASSIGN` reads only the files. A gap on a file, and a file that no
    # component owns, still hold or fail it.
    "typescript unresolved import gap": (
        TYPESCRIPT,
        {"src/a/x.ts": UNRESOLVED},
        {"ASSIGN": "PASS", "A-NO-B": "UNKNOWN"},
    ),
    "typescript unresolved import gap and a file outside every component": (
        TYPESCRIPT,
        {"src/a/x.ts": UNRESOLVED, "src/c/z.ts": "export const z = 1;\n"},
        {"ASSIGN": "FAIL", "A-NO-B": "UNKNOWN"},
    ),
    "typescript unresolved import gap and a generated file outside every component": (
        TYPESCRIPT,
        {"src/a/x.ts": UNRESOLVED, "src/c/gen.d.ts": "export declare const g: number;\n"},
        {"ASSIGN": "FAIL", "A-NO-B": "UNKNOWN"},
    ),
    "typescript unresolved import gap and a generated file of a component": (
        TYPESCRIPT,
        {"src/a/x.ts": UNRESOLVED, "src/a/gen.d.ts": "export declare const g: number;\n"},
        {"ASSIGN": "PASS", "A-NO-B": "UNKNOWN"},
    ),
    "typescript unresolved import gap and a syntax error gap": (
        TYPESCRIPT,
        {"src/a/x.ts": UNRESOLVED, "src/a/bad.ts": "export const = ;\n"},
        {"ASSIGN": "UNKNOWN", "A-NO-B": "UNKNOWN"},
    ),
    "dart clean": (DART, {}, {"ASSIGN": "PASS", "A-NO-B": "PASS"}),
    "dart gap": (DART, {"pubspec.yaml": WORKSPACE}, {"ASSIGN": "PASS", "A-NO-B": "UNKNOWN"}),
    "dart seen violation beside the gap": (
        DART,
        {"pubspec.yaml": WORKSPACE, "lib/src/a/x.dart": DART.uses_b},
        {"ASSIGN": "PASS", "A-NO-B": "FAIL"},
    ),
    # A second package in a scan root can own its files, so the gap states no effect.
    "dart gap without an effect": (
        DART,
        {"lib/src/b/pubspec.yaml": "name: other\n"},
        {"ASSIGN": "UNKNOWN", "A-NO-B": "UNKNOWN"},
    ),
}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_gap_holds_the_rules_that_read_its_effect(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    language, more, expected = PLANTS[name]
    result = verdict(release_core, project(tmp_path, language, more))
    assert rows(result) == expected, result["frame"].get("explained")
    gaps = result["frame"]["collection_gaps"]
    assert bool(gaps) == ("gap" in name), gaps


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs a file that cannot be read")
def test_an_unreadable_source_holds_the_assignment_beside_a_resolution_gap(
    release_core: Path, tmp_path: Path
) -> None:
    root = project(tmp_path, TYPESCRIPT, {"src/a/x.ts": UNRESOLVED})
    (root / "src/a/x.ts").chmod(0)
    try:
        result = verdict(release_core, root)
    finally:
        (root / "src/a/x.ts").chmod(0o644)
    assert rows(result)["ASSIGN"] == "UNKNOWN", result["frame"].get("explained")
