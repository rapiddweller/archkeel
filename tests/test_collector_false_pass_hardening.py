# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1048: a real violation in a TypeScript, Dart or Rust project is never PASS.

Consumer: `archkeel validate` through the release core. Each plant is a violation that the
language tool runs or accepts: node runs the TypeScript files (type stripping), `dart analyze`
and `dart run` check the Dart files, and `cargo check` checks the Rust files. The rule must say
FAIL or UNKNOWN. A plant that gets PASS is a real false PASS: it is an expected failure with the
issue text in its `reason`, and no collector changes here.

Holes (MATRIX.md): 4 and 5 a hidden forbidden edge beside an effect-stated gap, 6 a forbidden
construct, 7 a file that `root_layout` does not allow, 9 a private import across components, and
10 a real cycle behind an effect-stated gap.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from corpus_support import commit_tree
from test_cli_native_python_imports import rows, verdict

GRAPH = "# Target\n\n<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n    a --> b\n```\n"
CYCLE_GRAPH = GRAPH.replace("a --> b\n", "a --> b\n    b --> a\n")
STAMP = "B-LOADED"
# A computed key that can name `constructor` can write any global: no free name is proven.
WRITES_ANY_GLOBAL = (
    "export const call = (o: any, k: string) => o[k]();\nexport const m = Math.min(1, 2);\n"
)
TS_CONFIG = json.dumps(
    {
        "compilerOptions": {
            "target": "ES2022",
            "module": "esnext",
            "moduleResolution": "bundler",
            "allowImportingTsExtensions": True,
            "noEmit": True,
        },
        "include": ["src"],
    }
)
TS_FILES = {
    "tsconfig.json": TS_CONFIG,
    "package.json": '{"name": "app", "private": true, "type": "module"}\n',
}
DART_FILES = {"pubspec.yaml": "name: app\nenvironment:\n  sdk: ^3.5.0\n"}
# A workspace key makes `package:` URIs resolve in packages that the survey does not read.
DART_GAP = "name: app\nworkspace:\n  - other\nenvironment:\n  sdk: ^3.5.0\n"
RULE = {"rationale": "r", "provenance": ["p"], "decided_by": "architect"}


def component(label: str, prefix: str, *, public: list[str] | None = None, needs: tuple = ()):
    """A component that owns the package `prefix.label`."""
    found = {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [f"{prefix}.{label}"],
        "responsibilities": [label],
        "forbidden_responsibilities": [],
        "provenance": ["p"],
        "requires": [{"component": name, "rationale": "r"} for name in needs],
        "decided_by": "architect",
    }
    return {**found, "public": public} if public is not None else found


def scan(
    root: Path,
    config: str,
    files: dict[str, str],
    rules: list[dict],
    *,
    graph: str = GRAPH,
    b_public: str | None = None,
) -> Path:
    """Write a project with the components `a` and `b` and the rules; commit it."""
    prefix = "app.src"
    own = f"{prefix}.b" if b_public is None else b_public
    parts = [
        component("a", prefix, needs=("b",), public=[f"{prefix}.a"]),
        component("b", prefix, public=[own]),
    ]
    contract = {"schema_version": "2.2.0", "components": parts, "rules": rules}
    written = {
        "archkeel.toml": f'[scan]\n{config}contract = "architecture-contract.json"\n',
        "architecture-contract.json": json.dumps(contract),
        "p": graph,
        **files,
    }
    for name, text in written.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    commit_tree(root)
    return root


TS = 'language = "typescript"\nroots = ["src"]\nnamespace = "app"\ntsconfig = "tsconfig.json"\n'
DART = 'language = "dart"\nroots = ["lib"]\nnamespace = "app"\n'
NO_A_TO_B = {
    **RULE,
    "id": "A-NO-B",
    "kind": "forbidden_dependency",
    "include_type_checking": True,
}
CYCLES = {**RULE, "id": "NO-CYCLES", "kind": "no_component_cycles"}
INTERFACE = {**RULE, "id": "BOUNDARY", "kind": "interface_boundary"}


def never_pass(root: Path, release_core: Path, rule_id: str) -> str:
    """The verdict of one rule; the caller asserts the verdict that the real program shows."""
    return rows(verdict(release_core, root))[rule_id]


def node(root: Path, entry: str) -> str:
    """Run a TypeScript entry with node (type stripping) and return what it prints."""
    done = subprocess.run(
        ["node", "--experimental-strip-types", entry],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def dart(root: Path, *arguments: str) -> str:
    """Run the Dart tool in a project; a failing analysis or run fails the plant."""
    done = subprocess.run(
        ["dart", *arguments], cwd=root, capture_output=True, text=True, check=False, timeout=240
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is the oracle")
needs_dart = pytest.mark.skipif(shutil.which("dart") is None, reason="dart is the oracle")
needs_cargo = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")


# --- TypeScript: node runs each plant ----------------------------------------------------------
B_LOADS = f"console.log('{STAMP}');\nexport const y = 1;\n"
TS_HIDDEN = {
    "global-write": (
        {
            "src/a/x.ts": "export const read = () => (globalThis as any).shared;\n",
            "src/b/y.ts": f"(globalThis as any).shared = '{STAMP}';\n",
            "src/main.ts": "import './b/y.ts';\nimport { read } from './a/x.ts';\n"
            "console.log(read());\n",
        },
        True,
    ),
    "create-require": (
        {
            "src/a/x.ts": "import { createRequire } from 'node:module';\n"
            "export const y = createRequire(import.meta.url)('../b/y.ts');\n",
            "src/b/y.ts": B_LOADS,
            "src/main.ts": "import './a/x.ts';\n",
        },
        False,
    ),
    "computed-import": (
        {
            "src/a/x.ts": "export const load = () => import('../b/' + 'y.ts');\n",
            "src/b/y.ts": B_LOADS,
            "src/main.ts": "import { load } from './a/x.ts';\nawait load();\n",
        },
        False,
    ),
}


@needs_node
@pytest.mark.parametrize("gap", [True, False], ids=["with-gap", "no-gap"])
@pytest.mark.parametrize("name", sorted(TS_HIDDEN))
def test_a_hidden_typescript_edge_is_never_pass(
    release_core: Path, tmp_path: Path, name: str, gap: bool
) -> None:
    files, _ = TS_HIDDEN[name]
    files = {**TS_FILES, **files}
    if gap:
        files["src/b/y.ts"] += WRITES_ANY_GLOBAL
    root = scan(tmp_path, TS, files, [{**NO_A_TO_B, "source": "app.src.a", "target": "app.src.b"}])
    assert STAMP in node(root, "src/main.ts"), "node must load b: the edge is real"
    assert never_pass(root, release_core, "A-NO-B") in {"FAIL", "UNKNOWN"}


TS_CONSTRUCTS = {
    "eval": "export const v = eval('1 + 1');\n",
    "any_annotation": "export const v: any = 1;\n",
    "dynamic_import": "export const v = (n: string) => import(n);\n",
}


@needs_node
@pytest.mark.parametrize("construct", sorted(TS_CONSTRUCTS))
def test_a_forbidden_typescript_construct_is_never_pass(
    release_core: Path, tmp_path: Path, construct: str
) -> None:
    files = {
        **TS_FILES,
        "src/a/x.ts": TS_CONSTRUCTS[construct],
        "src/b/y.ts": "export const y = 1;",
    }
    rule_ = {
        **RULE,
        "id": "CONSTRUCT",
        "kind": "forbidden_construct",
        "source": "app.src.a",
        "constructs": [construct],
    }
    root = scan(tmp_path, TS, files, [rule_])
    node(root, "src/a/x.ts")
    assert never_pass(root, release_core, "CONSTRUCT") in {"FAIL", "UNKNOWN"}


@needs_node
def test_a_typescript_file_that_the_layout_does_not_allow_is_never_pass(
    release_core: Path, tmp_path: Path
) -> None:
    files = {
        **TS_FILES,
        "src/a/x.ts": "export const x = 1;\n",
        "src/a/extra.ts": "export const extra = 1;\n",
        "src/b/y.ts": "export const y = 1;\n",
    }
    rule_ = {
        **RULE,
        "id": "LAYOUT",
        "kind": "root_layout",
        "root": "app.src.a",
        "allowed_children": ["app.src.a.x_x2e_ts"],
    }
    root = scan(tmp_path, TS, files, [rule_])
    node(root, "src/a/extra.ts")
    assert never_pass(root, release_core, "LAYOUT") == "FAIL"


@needs_node
def test_a_private_typescript_import_across_components_is_never_pass(
    release_core: Path, tmp_path: Path
) -> None:
    files = {
        **TS_FILES,
        "src/a/x.ts": "import { secret } from '../b/impl.ts';\nexport const x = secret;\n",
        "src/b/api.ts": "export const api = 1;\n",
        "src/b/impl.ts": "export const secret = 2;\n",
        "src/main.ts": "import { x } from './a/x.ts';\nconsole.log(x);\n",
    }
    root = scan(tmp_path, TS, files, [INTERFACE], b_public="app.src.b.api_x2e_ts")
    assert node(root, "src/main.ts").strip() == "2"
    assert never_pass(root, release_core, "BOUNDARY") == "FAIL"


@needs_node
@pytest.mark.parametrize("gap", [True, False], ids=["with-gap", "no-gap"])
def test_a_typescript_cycle_behind_a_gap_is_never_pass(
    release_core: Path, tmp_path: Path, gap: bool
) -> None:
    files = {
        **TS_FILES,
        "src/a/x.ts": "import { y } from '../b/y.ts';\nexport const x = 1;\n"
        "export const z = () => y;\n",
        "src/b/y.ts": "import { x } from '../a/x.ts';\nexport const y = 2;\n"
        "export const w = () => x;\n" + (WRITES_ANY_GLOBAL if gap else ""),
        "src/main.ts": "import { x } from './a/x.ts';\nconsole.log(x);\n",
    }
    root = scan(tmp_path, TS, files, [CYCLES], graph=CYCLE_GRAPH)
    assert node(root, "src/main.ts").strip() == "1"
    assert never_pass(root, release_core, "NO-CYCLES") == "FAIL"
