# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep recursive boundary checks from rescanning all imports per facade function."""

import json
from pathlib import Path
from unittest.mock import patch

from test_recursive_inside_independent_contracts import _write_three_levels

import archkeel.check.evaluation.rules as boundary_violations
from archkeel.cli.observe import analyze_snapshot


def test_recursive_boundary_indexes_do_not_scale_with_public_function_count(
    tmp_path: Path,
) -> None:
    import_lines = [
        "from sample.layer.target.api import Payload",
        *(f"import sample.layer.target.api as dep_{index}" for index in range(20)),
    ]
    functions = [f"def run_{index}(value: Payload) -> str:\n    return ''" for index in range(20)]
    _write_three_levels(
        tmp_path,
        source_import="\n".join(import_lines) + "\n\n" + "\n\n".join(functions),
    )
    rule = {
        "id": "SOURCE-TYPES",
        "kind": "boundary_types",
        "source": "sample.layer.source",
        "rationale": "Keep the source API typed.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    for relative in ("contract.json", "contracts/one.json", "contracts/two.json"):
        path = tmp_path / relative
        contract = json.loads(path.read_text())
        contract["rules"].append(rule)
        contract["components"][0]["public"] = [
            f"sample.layer.source.api:run_{index}" for index in range(20)
        ]
        path.write_text(json.dumps(contract))

    original = boundary_violations._reexport_facade_entries
    fallback_rows = 0
    indexed_rows = 0

    def count_fallback_rows(*args, **kwargs):
        nonlocal fallback_rows
        imports = args[3]
        reexports = args[5] if len(args) > 5 else kwargs.get("reexports")
        if reexports is None:
            fallback_rows += len(imports)
        return original(*args, **kwargs)

    index = boundary_violations._reexport_index

    def count_index_rows(imports):
        nonlocal indexed_rows
        indexed_rows += len(imports)
        return index(imports)

    with (
        patch.object(
            boundary_violations, "_reexport_facade_entries", side_effect=count_fallback_rows
        ),
        patch.object(boundary_violations, "_reexport_index", side_effect=count_index_rows),
    ):
        model, exit_code = analyze_snapshot(
            tmp_path,
            git_head="a" * 40,
            dirty=False,
            contract_root=tmp_path,
            contract_path=tmp_path / "contract.json",
            roots=("sample",),
            namespace="sample",
        )

    assert exit_code == 0
    import_count = len(model["imports"])
    assert import_count > 0
    assert fallback_rows <= import_count, (
        f"recursive boundary checks rescanned {fallback_rows} import rows "
        f"for {import_count} imports and 20 public functions"
    )
    # Three contract levels each run at most four boundary passes, not one per function.
    assert indexed_rows <= import_count * 12, (
        f"recursive boundary checks rebuilt indexes over {indexed_rows} import rows "
        f"for {import_count} imports and 20 public functions"
    )
