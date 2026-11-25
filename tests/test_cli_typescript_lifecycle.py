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
from test_cli_native_python_imports import command, verdict

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


def tree(root: Path, source: str, *, requires_only: bool = False) -> Path:
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
    if requires_only:
        components[1]["public"] = ["app.src.b"]
        rules = rules[1:]
        source = "import { t } from '../b/t';\nexport const base = t;\n" + source
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
    result = verdict(release_core, tree(tmp_path, source, requires_only=True))
    assert result["frame"]["rules"]["REQUIRES"][1] == expected
    if expected == "UNKNOWN":
        assert result["frame"]["explained"]["REQUIRES"]
    else:
        assert result["status"] == "PASS"


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


def test_usage_unknown_names_the_action_of_each_entry(release_core: Path, tmp_path: Path) -> None:
    """#1963: an entry whose module has an import is not the same as one that no import reaches."""
    root = tmp_path / "p"
    root.mkdir()
    tree(root, "import type { TT } from '../b/t';\nexport type X = TT;\n")
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["components"][1]["public"] = [
        "app.src.b.t_x2e_ts:t",
        "app.src.b.t_x2e_ts:TT",
        "app.src.b.other_x2e_ts:o",
        "app.src.b.other_x2e_ts",
    ]
    path.write_text(json.dumps(contract))
    (root / "src/b/other.ts").write_text("export const o = 1;\n")
    commit_tree(root)
    result = verdict(release_core, root)
    rows = [g for g in result["frame"]["gaps"] if g["kind"] == "interface.usage_unknown"]
    found = {g["subject"].rsplit("/", 1)[-1]: g["action"] for g in rows}
    assert found == {
        "2:app.src.b.other_x2e_ts:o": "no_import_found",
        "3:app.src.b.other_x2e_ts": "no_import_found",
        "0:app.src.b.t_x2e_ts:t": "import_seen",
    }, rows
    assert all("action" not in g for g in result["frame"]["gaps"] if g not in rows)
    text = command(release_core, root, "--text", verb="validate").stdout
    assert "      2 x no import found: delete the entry or name the importer" in text
    assert "      1 x import seen, no proven use: read the import or delete the entry" in text
