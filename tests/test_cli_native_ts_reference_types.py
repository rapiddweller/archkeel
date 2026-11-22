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
TYPE_ROOTS_NODE_MODULES = (
    '{"compilerOptions":{"allowJs":true,"typeRoots":["./node_modules/custom"]},"include":["src"]}'
)
TYPE_ROOTS_EMPTY = '{"compilerOptions":{"allowJs":true,"typeRoots":[]},"include":["src"]}'
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
    "no-default-lib-false": (
        {**INSTALLED, "src/a/a.ts": DIRECTIVE.replace(" />", ' no-default-lib="false" />')},
        "vite",
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
    "no-default-lib-true-with-types": (
        {**INSTALLED, "src/a/a.ts": DIRECTIVE.replace(" />", ' no-default-lib="true" />')},
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
# The compiler picks `custom/foo`; the collector would record `@types/foo`.
FOO = {
    "node_modules/custom/foo/index.d.ts": "declare const c: number;\n",
    "node_modules/@types/foo/index.d.ts": "declare const t: number;\n",
    "src/a/a.ts": '/// <reference types="foo" />\nexport const a = 1;\n',
}
# `@types/foo` has `typesVersions`, which the resolver does not model; `foo` is installed too.
TYPES_VERSIONS = {
    "node_modules/@types/foo/package.json": (
        '{"name":"@types/foo","version":"1.0.0","types":"index.d.ts",'
        '"typesVersions":{"*":{"*":["ts4/*"]}}}'
    ),
    "node_modules/@types/foo/index.d.ts": "declare const t: number;\n",
    "node_modules/@types/foo/ts4/index.d.ts": "declare const t4: number;\n",
    "node_modules/foo/index.d.ts": "declare const f: number;\n",
    "src/a/a.ts": '/// <reference types="foo" />\nexport const a = 1;\n',
}
# `types` names a missing declaration, so tsc reports TS2688; general resolution finds `index.js`.
MISSING_DECLARATION = {
    "node_modules/bad/index.js": "exports.x = 1;\n",
    "node_modules/bad/package.json": (
        '{"name":"bad","version":"1.0.0","main":"index.js","types":"missing.d.ts"}'
    ),
    "src/a/a.ts": '/// <reference types="bad" />\nexport const a = 1;\n',
}
GAPS = {
    "type-roots-set": (
        {**FOO, "tsconfig.json": TYPE_ROOTS_NODE_MODULES},
        "@types/foo",
    ),
    "type-roots-empty-list": (
        {**INSTALLED, "tsconfig.json": TYPE_ROOTS_EMPTY, "src/a/a.ts": DIRECTIVE},
        "vite",
    ),
    "types-versions-before-an-installed-fallback": (TYPES_VERSIONS, "@types/foo"),
    "types-field-names-a-missing-declaration": (MISSING_DECLARATION, "bad"),
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


def _project(root: Path, files: dict[str, str], dependency: str, anchor: bool = False) -> Path:
    # AD-1048: a PASS needs one import that names the package. The allowed source `b` is the
    # honest user, so that the rule has an import to examine and `a` shows no edge of its own.
    if anchor:
        files = {
            **files,
            "src/b/anchor.ts": f'import type {{}} from "{dependency}";\nexport const anchor = 1;\n',
        }
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
    files = {**INSTALLED, "src/a/a.ts": "export const a = 1;\n"}
    assert _status(_project(tmp_path, files, "vite", anchor=True), release_core) == "PASS"


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
    root = _project(tmp_path, {**INSTALLED, **files}, dependency, anchor=True)
    assert _status(root, release_core) == "PASS", name


def test_a_package_that_no_import_names_is_not_pass(tmp_path: Path, release_core: Path) -> None:
    """AD-1048: with no import of the package, the rule examines nothing."""
    files = {"src/a/a.ts": "export const a = 1;\n"}
    assert _status(_project(tmp_path, files, "vite"), release_core) == "UNKNOWN"


@pytest.mark.parametrize("name", sorted(GAPS))
def test_a_directive_that_is_not_proven_to_one_installed_package_is_a_named_gap(
    tmp_path: Path, release_core: Path, name: str
) -> None:
    files, dependency = GAPS[name]
    assert _status(_project(tmp_path, files, dependency), release_core) == "UNKNOWN", name
