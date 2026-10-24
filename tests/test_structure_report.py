# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Neutral structure views retain Core measurements and component navigation."""

import re
from dataclasses import replace

import pytest
from test_atlas_report import _page, _result
from test_module_explore import _sample

from archkeel.ir.codec import canonical_report_bytes
from archkeel.ir.structure import oversized_insides, structure_metrics
from archkeel.render.html import _atlas_content, render_html


def _sparse_component(tmp_path, *, internal_edge=False):
    return _sample(
        tmp_path,
        extra_files={
            f"sample/core/resource{index}.py": (
                "import sample.core\n" if internal_edge and index == 0 else "VALUE = 1\n"
            )
            for index in range(16)
        },
    )


def _overview(document):
    match = re.search(
        r'<details class="report-section report-evidence atlas-structure-overview">(.*?)</details>',
        document,
        re.S,
    )
    assert match is not None, "The report needs a neutral Structure overview"
    return match.group(1)


@pytest.mark.parametrize("internal_edge", [False, True])
def test_structure_overview_keeps_every_component_measurement_without_size_inference(
    tmp_path, internal_edge
):
    model = _sparse_component(tmp_path, internal_edge=internal_edge)
    encoded = canonical_report_bytes(model)
    claim = oversized_insides(model)
    assert {item.scope for item in claim.candidates} == {"core"}
    assert claim.candidates[0].modules == 17
    assert claim.candidates[0].inner_edges == int(internal_edge)

    overview = _overview(_page(model))
    assert "<summary>Structure overview</summary>" in overview
    assert (
        "Top-level context: 2 declared components and 1 observed cross-component edge." in overview
    )
    metrics = [item for item in structure_metrics(model) if item.level == "component"]
    components = {item.label: item.id for item in _result(model).architecture_projection.components}
    for metric in metrics:
        assert (
            f'<a href="?component={components[metric.scope]}" '
            f'data-atlas-component-route="{components[metric.scope]}">{metric.scope}</a>'
        ) in overview
        assert (
            f'<td class="numeric">{metric.modules}</td>'
            f'<td class="numeric">{metric.inner_edges}</td>'
            f'<td class="numeric">{metric.fan_in}</td>'
            f'<td class="numeric">{metric.fan_out}</td>'
            '<td class="numeric">no calls</td>'
        ) in overview
    assert overview.count("<tr>") == len(metrics) + 1
    for inferred in ("candidate", "Review question", "larger than", "split", "PASS", "FAIL"):
        assert inferred not in overview
    assert canonical_report_bytes(model) == encoded
    assert oversized_insides(model) == claim


@pytest.mark.parametrize("missing", ["modules", "dependency_edges"])
def test_structure_overview_names_unavailable_measurements(tmp_path, missing):
    model = _sample(tmp_path)
    model = replace(model, sections=tuple(item for item in model.sections if item.name != missing))

    overview = _overview(
        _atlas_content(
            _result(model), model, {}, repository="sample", architecture_href="architecture.json"
        )
    )
    assert "Not available:" in overview
    assert "UNKNOWN" not in overview
    if missing == "modules":
        assert "this observation records no modules" in overview
        assert "<table" not in overview
    else:
        assert "this observation records no dependency edges" in overview
        assert "observed cross-component edges: n/a" in overview
        assert overview.count('<td class="numeric">n/a</td>') == 6
        assert overview.count('<td class="numeric">1</td>') == 2


def test_legacy_evidence_report_also_uses_neutral_structure_overview(tmp_path):
    model = _sparse_component(tmp_path)
    document = render_html(
        _result(model), model, repository="sample", architecture_href="architecture.json"
    ).decode()

    assert "<h2>Structure overview</h2>" in document
    assert "components larger than their level" not in document
    assert "Review claim: symbols nobody references" in document
    assert "Edges inside" in document and "Unresolved calls" in document
    assert "<code>sample.core</code>" in document
