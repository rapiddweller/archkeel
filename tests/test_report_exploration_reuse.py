# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One report invocation shares its immutable module exploration across both pages."""

from dataclasses import replace

import pytest
from test_atlas_report import _result
from test_module_explore import _sample

from archkeel.ir.codec import canonical_report_bytes
from archkeel.render import atlas
from archkeel.render import html as renderer


def test_page_pair_reuses_one_exploration_without_changing_either_html(tmp_path, monkeypatch):
    model = _sample(tmp_path, uml=True)
    result = _result(model)
    encoded = canonical_report_bytes(model)
    options = {"repository": "One target", "architecture_href": "architecture.json"}
    expected = renderer.render_architecture_details(result, encoded, **options)
    expected["architecture.report.html"] = renderer.render_architecture_html(
        result, encoded, **options
    )
    calls = []
    derive = renderer.module_exploration

    def counted(observation, *, report):
        calls.append(observation.source)
        return derive(observation, report=report)

    monkeypatch.setattr(renderer, "module_exploration", counted)
    monkeypatch.setattr(atlas, "module_exploration", counted)

    assert dict(renderer.render_architecture_pages(result, encoded, **options)) == expected
    assert calls == [model.source]
    assert dict(renderer.render_architecture_pages(result, encoded, **options)) == expected
    assert calls == [model.source, model.source]


def test_mismatched_projection_is_rejected_before_expensive_exploration(tmp_path, monkeypatch):
    model = _sample(tmp_path, uml=True)
    result = _result(model)
    assert result.architecture_projection is not None
    source = replace(result.architecture_projection.source, git_head="b" * 40)
    result = replace(
        result, architecture_projection=replace(result.architecture_projection, source=source)
    )
    calls = []

    def unexpected(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Projection validation must precede exploration")

    monkeypatch.setattr(renderer, "module_exploration", unexpected)
    monkeypatch.setattr(atlas, "module_exploration", unexpected)
    with pytest.raises(ValueError, match="matching authenticated Core projection"):
        renderer.render_architecture_pages(
            result,
            canonical_report_bytes(model),
            repository="One target",
            architecture_href="architecture.json",
        )
    assert calls == []
