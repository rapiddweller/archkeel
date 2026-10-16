# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The HTML executes a checked derivative of one authored Flow program."""

import json
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest
from test_atlas_report import _page, _sample


def test_report_identifies_the_current_flow_source_derivative(tmp_path):
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    expected = f"// Generated from flow.js; source-sha256={sha256(source.read_bytes()).hexdigest()}"
    page = _page(_sample(tmp_path))
    assert expected in page


@pytest.fixture
def publisher():
    from tools import browser_runtime

    if shutil.which("node") is None or not browser_runtime._COMPILER.is_file():
        pytest.skip("Run make browser-runtime-install for publication compiler tests")
    return browser_runtime


def test_locked_publication_disables_optimization_and_name_changes():
    root = Path(__file__).parents[1]
    options = json.loads((root / "tools/browser-runtime/options.json").read_bytes())
    assert options["compress"] is False
    assert options["mangle"] is False
    assert options["keep_fnames"] is True
    assert options["keep_classnames"] is True
    assert options["format"]["comments"] is False


def test_committed_flow_runtime_is_deterministic_and_check_is_read_only(publisher):
    authored = {
        path: path.read_bytes()
        for path in publisher._ASSETS.glob("*.js")
        if path != publisher._OUTPUT
    }
    emitted = publisher._OUTPUT.read_bytes()
    assert publisher.runtime_bytes() == emitted
    assert publisher.runtime_bytes() == emitted
    publisher.check()
    assert publisher._OUTPUT.read_bytes() == emitted
    assert {path: path.read_bytes() for path in authored} == authored


def test_current_source_change_makes_unchanged_derivative_stale(publisher, tmp_path, monkeypatch):
    source = tmp_path / "flow.js"
    output = tmp_path / "flow.runtime.js"
    source.write_bytes(publisher._SOURCE.read_bytes() + b"\n// Updated authored source.\n")
    emitted = publisher._OUTPUT.read_bytes()
    output.write_bytes(emitted)
    monkeypatch.setattr(publisher, "_SOURCE", source)
    monkeypatch.setattr(publisher, "_OUTPUT", output)
    with pytest.raises(SystemExit, match="stale"):
        publisher.check()
    assert output.read_bytes() == emitted


def test_published_flow_preserves_actual_ast_and_rejects_semantic_mutations(publisher):
    node = shutil.which("node")
    assert node is not None
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            node,
            str(root / "tests/browser_runtime_ast.cjs"),
            str(publisher._TOOLS / "node_modules"),
            str(publisher._SOURCE),
            str(publisher._OUTPUT),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    print(result.stdout)
