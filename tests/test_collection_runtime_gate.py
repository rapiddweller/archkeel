# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The same required-runtime gate applies to every configured collector."""

import json
import sys
from pathlib import Path

import pytest
from test_source_namespace_acceptance import _GIT_HEAD, _response

from archkeel.analyzer.process import ProcessCollector
from archkeel.check.observe import Observer


@pytest.mark.parametrize("language", ["python", "dart", "typescript"])
@pytest.mark.parametrize("version", ["20.0.0", "22.23.3", "24.1.0", "26.0.0"])
def test_required_runtime_is_checked_for_every_collector(
    tmp_path: Path, language: str, version: str
) -> None:
    root = tmp_path / "repo"
    source = root / "src"
    source.mkdir(parents=True)
    if language == "python":
        source = source / "project"
        source.mkdir()
        (source / "app.py").write_text("value = 1\n")
    elif language == "dart":
        (root / "pubspec.yaml").write_text("name: project\n")
        (source / "app.dart").write_text("class Value {}\n")
    response = _response(language, root)
    response["facts"]["runtime"].update(
        {
            "name": "node",
            "version": version,
            "required": ">=22.13,<23 || >=24,<25 || >=26",
        }
    )
    contract = root / "contract.json"
    contract.write_text('{"schema_version":"2.1.0","components":[],"rules":[]}')
    output = json.dumps(response)
    result = Observer(ProcessCollector((sys.executable, "-B", "-c", f"print({output!r})")))(
        root,
        roots=("src",),
        namespace="project",
        contract="contract.json",
        git_head=_GIT_HEAD,
        dirty=False,
        contract_root=root,
        language=language,
    )
    assert result.observation is not None
    assert any(item.kind == "runtime_mismatch" for item in result.diagnostics) == (
        version == "20.0.0"
    )
    assert result.observation.runtime.name == "node"
    assert result.observation.runtime.version == version
    assert result.observation.runtime.required == ">=22.13,<23 || >=24,<25 || >=26"


@pytest.mark.parametrize(
    "required", [None, "", " ", "||>=22", ">=22||", ">=22||||<23", ">=22||invalid"]
)
def test_missing_or_malformed_runtime_requirements_cannot_pass(required: str | None) -> None:
    from archkeel.check.runtime import runtime_diagnostic
    from archkeel.ir.facts import RuntimeInfo

    assert runtime_diagnostic(RuntimeInfo("node", "22.23.3", required)) is not None


@pytest.mark.parametrize("version", ["22.12.9", "23.0.0", "25.0.0"])
def test_versions_between_supported_node_ranges_cannot_pass(version: str) -> None:
    from archkeel.check.runtime import runtime_diagnostic
    from archkeel.ir.facts import RuntimeInfo

    assert (
        runtime_diagnostic(RuntimeInfo("node", version, ">=22.13,<23 || >=24,<25 || >=26"))
        is not None
    )


def test_html_names_the_actual_collector_runtime_and_requirement() -> None:
    from dataclasses import replace

    from test_delta import _model

    from archkeel.ir.codec import parse_observation
    from archkeel.ir.facts import RuntimeInfo
    from archkeel.ir.model import RunResult
    from archkeel.render.html import render_html

    observation = replace(
        parse_observation(_model(git_head="a" * 40)),
        python_version=None,
        runtime=RuntimeInfo("node", "22.23.3", ">=22.13,<23"),
    )
    page = render_html(
        RunResult("report", 0), observation, repository="fixture", architecture_href=None
    ).decode()
    assert "node 22.23.3" in page
    assert "&gt;=22.13,&lt;23" in page
