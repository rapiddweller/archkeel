# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Recursive source evidence remains local in the standard report."""

import json
from pathlib import Path

from graph_report_support import import_sites
from test_analyzer import _component, _observe

from archkeel.ir.report_graph import architecture_report


def test_inside_import_site_evidence_is_scoped_to_its_parent_level(tmp_path: Path) -> None:
    def inner_contract(parent: str) -> dict[str, object]:
        return {
            "schema_version": "2.1.0",
            "components": [
                {
                    "id": f"COMP-{parent.upper()}-A",
                    "label": "a",
                    "role": "component",
                    "packages": [f"sample.{parent}.a"],
                    "responsibilities": [],
                    "forbidden_responsibilities": [],
                    "provenance": ["docs/architecture/sample.md"],
                },
                {
                    "id": f"COMP-{parent.upper()}-B",
                    "label": "b",
                    "role": "component",
                    "packages": [f"sample.{parent}.b"],
                    "responsibilities": [],
                    "forbidden_responsibilities": [],
                    "provenance": ["docs/architecture/sample.md"],
                },
            ],
            "rules": [],
        }

    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component("core") | {"inside": "core-inner.json"},
                    _component("service") | {"inside": "service-inner.json"},
                ],
                "rules": [],
            }
        )
    )
    for parent in ("core", "service"):
        (tmp_path / f"{parent}-inner.json").write_text(json.dumps(inner_contract(parent)))
        package = tmp_path / "sample" / parent
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        for child in ("a", "b"):
            child_package = package / child
            child_package.mkdir()
            (child_package / "__init__.py").write_text("")
        (package / "a/__init__.py").write_text(f"import sample.{parent}.b\n")
        (package / "b/__init__.py").write_text("")

    result = _observe(tmp_path)
    assert result.observation is not None
    report = architecture_report(result.observation)
    assert report.observed is not None
    evidence = {item.id: item for item in report.observed.evidence}
    for parent in ("core", "service"):
        sites = import_sites(report, f"sample.{parent}.a", f"sample.{parent}.b")
        assert len(sites) == 1
        assert [(evidence[item].file, evidence[item].line) for item in sites[0].evidence_ids] == [
            (f"sample/{parent}/a/__init__.py", 1)
        ]
