# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A leading `/// <reference types="name" />` is a type-only edge or a named gap (#686, AD-528).

Consumer: `archkeel validate` on a TypeScript project, through the release core. The contract lets
only `b` use one package (`external_dependency_scope`), and `a` holds the directive. The compiler
reads `@types/<name>` first and then the package `name`; the resolver proves the first one that is
installed, and the file then depends on that package: the rule FAILs. A directive that the resolver
does not prove to one installed package is a named gap: the rule is UNKNOWN. A directive after
code is not honored by the compiler: no edge, no gap. The control `import type` gives the same FAIL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree
from test_collector_false_pass_sources import BASE, CONTRACT

from archkeel.cli import core_only

DIRECTIVE = '/// <reference types="vite/client" />\nexport const a = 1;\n'
INSTALLED = {
    "node_modules/vite/client.d.ts": "declare const v: number;\n",
    "node_modules/vite/package.json": '{"name":"vite","version":"5.0.0","types":"client.d.ts"}',
}
SCOPED = {
    "node_modules/@scope/pkg/index.d.ts": "declare const s: number;\n",
    "node_modules/@scope/pkg/package.json": (
        '{"name":"@scope/pkg","version":"1.0.0","types":"index.d.ts"}'
    ),
}
PATHS = (
    '{"compilerOptions":{"allowJs":true,"baseUrl":".","paths":{"vite/*":["src/b/*"]}},'
    '"include":["src"]}'
)
TYPE_ROOTS = '{"compilerOptions":{"allowJs":true,"typeRoots":["./src"]},"include":["src"]}'

# Plant -> (files, the package that the rule guards).
EDGES = {
    "installed": ({**INSTALLED, "src/a/a.ts": DIRECTIVE}, "vite"),
    "after-a-comment": ({**INSTALLED, "src/a/a.ts": "// head\n/* more */\n" + DIRECTIVE}, "vite"),
    "after-a-hashbang": ({**INSTALLED, "src/a/a.ts": "#!/usr/bin/env node\n" + DIRECTIVE}, "vite"),
    "scoped-name": (
        {**SCOPED, "src/a/a.ts": '/// <reference types="@scope/pkg" />\nexport const a = 1;\n'},
        "@scope/pkg",
    ),
    "upper-case-tag": (
        {**INSTALLED, "src/a/a.ts": DIRECTIVE.replace("reference", "REFERENCE")},
        "vite",
    ),
    "second-directive": (
        {
            **INSTALLED,
            "src/a/a.ts": '/// <reference lib="es2020" />\n' + DIRECTIVE,
        },
        "vite",
    ),
    "javascript-file": ({**INSTALLED, "src/a/a.js": DIRECTIVE}, "vite"),
    "types-package-only": (
        {
            "node_modules/@types/jest/index.d.ts": "declare const j: number;\n",
            "src/a/a.ts": '/// <reference types="jest" />\nexport const a = 1;\n',
        },
        "@types/jest",
    ),
    "builtin-name-with-its-types-package": (
        {
            "node_modules/@types/node/index.d.ts": "declare const n: number;\n",
            "src/a/a.ts": '/// <reference types="node" />\nexport const a = 1;\n',
        },
        "@types/node",
    ),
    "scoped-types-package": (
        {
            "node_modules/@types/scope__pkg/index.d.ts": "declare const s: number;\n",
            "src/a/a.ts": '/// <reference types="@scope/pkg" />\nexport const a = 1;\n',
        },
        "@types/scope__pkg",
    ),
    "control-import-type": (
        {**INSTALLED, "src/a/a.ts": 'import type {} from "vite/client";\nexport const a = 1;\n'},
        "vite",
    ),
}
# The compiler does not honor these, or they are no `types` reference: no edge, no gap.
SILENT = {
    "after-code": (
        {**INSTALLED, "src/a/a.ts": 'export const a = 1;\n/// <reference types="vite/client" />\n'},
        "vite",
    ),
    "block-comment": (
        {
            **INSTALLED,
            "src/a/a.ts": '/* /// <reference types="vite/client" /> */\nexport const a = 1;\n',
        },
        "vite",
    ),
    "no-default-lib": (
        {
            **INSTALLED,
            "src/a/a.ts": '/// <reference no-default-lib="true" />\nexport const a = 1;\n',
        },
        "vite",
    ),
}
# A leading directive that the resolver does not prove, or that names a path: a named gap.
GAPS = {
    "package-not-installed": ({"src/a/a.ts": DIRECTIVE}, "vite"),
    "builtin-name-without-its-types-package": (
        {"src/a/a.ts": '/// <reference types="node" />\nexport const a = 1;\n'},
        "@types/node",
    ),
    "resolution-mode": (
        {**INSTALLED, "src/a/a.ts": DIRECTIVE.replace(" />", ' resolution-mode="import" />')},
        "vite",
    ),
    "name-with-a-space": (
        {**INSTALLED, "src/a/a.ts": DIRECTIVE.replace("vite/client", "vite client")},
        "vite",
    ),
    "empty-name": (
        {**INSTALLED, "src/a/a.ts": DIRECTIVE.replace("vite/client", "")},
        "vite",
    ),
    "relative-name": (
        {"src/a/a.ts": '/// <reference types="../b/t" />\nexport const a = 1;\n'},
        "vite",
    ),
    "path-form": (
        {"src/a/a.ts": '/// <reference path="../b/t.ts" />\nexport const a = 1;\n'},
        "vite",
    ),
    "name-that-paths-maps-to-the-project": (
        {
            "tsconfig.json": PATHS,
            "src/b/client.ts": "export const c = 1;\n",
            "src/a/a.ts": DIRECTIVE,
        },
        "vite",
    ),
    "type-root-in-the-project": (
        {**INSTALLED, "tsconfig.json": TYPE_ROOTS, "src/a/a.ts": DIRECTIVE},
        "vite",
    ),
}


def _project(root: Path, files: dict[str, str], dependency: str) -> Path:
    contract = json.loads(json.dumps(CONTRACT))
    contract["schema_version"] = "3.4.0"
    contract["rules"].append(
        {
            "id": "EXT",
            "kind": "external_dependency_scope",
            "dependency": dependency,
            "allowed_sources": ["app.src.b"],
            "rationale": f"Only b uses {dependency}.",
            "provenance": ["README.md"],
            "decided_by": "architect",
        }
    )
    for relative, text in {
        **BASE,
        "architecture-contract.json": json.dumps(contract),
        **files,
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    commit_tree(root)
    return root


def _status(root: Path, release_core: Path) -> str:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        _, document = run("validate", "--root", str(root))
    rules: dict[str, Any] = document["frame"]["rules"]
    return str(rules["EXT"][1])


def test_the_honest_project_keeps_its_pass(tmp_path: Path, release_core: Path) -> None:
    root = _project(tmp_path, {"src/a/a.ts": "export const a = 1;\n"}, "vite")
    assert _status(root, release_core) == "PASS"


@pytest.mark.parametrize("name", sorted(EDGES))
def test_a_leading_types_directive_is_a_type_only_edge(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    files, dependency = EDGES[name]
    assert _status(_project(tmp_path, files, dependency), release_core) == "FAIL", name


@pytest.mark.parametrize("name", sorted(SILENT))
def test_a_directive_that_the_compiler_does_not_honor_gives_no_edge(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    files, dependency = SILENT[name]
    assert _status(_project(tmp_path, files, dependency), release_core) == "PASS", name


@pytest.mark.parametrize("name", sorted(GAPS))
def test_a_directive_that_is_not_proven_to_one_installed_package_is_a_named_gap(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    files, dependency = GAPS[name]
    assert _status(_project(tmp_path, files, dependency), release_core) == "UNKNOWN", name
