# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-514: a `module:name` entry on TypeScript, decided by the tests of the core alone.

Release 4.0.1 gives `rule_unsupported_by_profile` for a symbol entry on TypeScript, so there is no
4.0.1 verdict to compare with. The core proves the use from the import `import { t } from '../b/t'`
and gives no lifecycle finding.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from corpus_support import commit_tree
from test_cli_native_python_imports import verdict

GRAPH = (
    "# Target\n\n<!-- archkeel-component-graph -->\n```mermaid\nflowchart LR\n"
    '    n_0["consumer"]\n    n_1["lib"]\n    n_0 --> n_1\n```\n'
)
BASE = {
    "role": "component",
    "responsibilities": ["Own the modules."],
    "forbidden_responsibilities": [],
    "provenance": ["docs/target.md"],
    "decided_by": "architect",
}


def tree(root: Path, source: str) -> Path:
    components = [
        {
            **BASE,
            "id": "consumer",
            "label": "consumer",
            "packages": ["app.src.a"],
            "requires": [{"component": "lib", "rationale": "Use it."}],
        },
        {
            **BASE,
            "id": "lib",
            "label": "lib",
            "packages": ["app.src.b"],
            "requires": [],
            "public": ["app.src.b.t_x2e_ts:t"],
        },
    ]
    rules = [
        {
            "id": "BOUNDARY",
            "kind": "interface_boundary",
            "rationale": "Callers use the declared interface.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
            "include_type_checking": True,
        },
        {
            "id": "REQUIRES",
            "kind": "complete_requires",
            "rationale": "Keep it.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        },
    ]
    files = {
        "archkeel.toml": (
            '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
        ),
        "tsconfig.json": '{"compilerOptions": {"strict": true}, "include": ["src"]}',
        "docs/target.md": GRAPH,
        "src/a/one.ts": source,
        "src/b/t.ts": "export const t = 1;\nexport type TT = number;\n",
        "architecture-contract.json": json.dumps(
            {"schema_version": "2.2.0", "components": components, "rules": rules}
        ),
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    commit_tree(root)
    return root


def codes(result: dict[str, object]) -> set[str]:
    rows = result["frame"]["unsupported"]["rules"]  # type: ignore[index]
    found = {re.match(r"hygiene:(interface\.\w+):", name) for name in rows}
    return {match.group(1) for match in found if match}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import { t } from '../b/missing';\nexport const used = t;\n", "UNKNOWN"),
        ("export const load = (name: string) => import(name);\n", "UNKNOWN"),
        ("export const alone = 1;\n", "PASS"),
    ],
)
def test_requires_with_typescript_import_limits(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    result = verdict(release_core, tree(tmp_path, source))
    assert result["frame"]["rules"]["REQUIRES"][1] == expected
    if expected == "UNKNOWN":
        assert result["frame"]["explained"]["REQUIRES"]


def test_a_symbol_entry_that_an_import_uses_gives_no_lifecycle_finding(
    release_core: Path, tmp_path: Path
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    result = verdict(
        release_core, tree(root, "import { t } from '../b/t';\nexport const used = t;\n")
    )
    assert codes(result) == set(), result["frame"]["unsupported"]


def test_a_symbol_entry_that_no_import_uses_is_usage_unknown(
    release_core: Path, tmp_path: Path
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    result = verdict(release_core, tree(root, "export const alone = 1;\n"))
    assert codes(result) == {"interface.usage_unknown"}, result["frame"]["unsupported"]
