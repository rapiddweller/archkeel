# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The HTML executes a checked derivative of one authored Flow program."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


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


def test_generated_publication_keeps_lf_on_every_checkout():
    root = Path(__file__).parents[1]
    paths = [
        "src/archkeel/render/assets/explorer.runtime.js",
        "src/archkeel/render/assets/report-graph-protocol.js",
        "src/archkeel/render/assets/report-graph-protocol.types.d.ts",
        "src/archkeel/render/assets/report-graph-vocabulary.ts",
        "tools/browser-runtime/protocol-exports.js",
        "tools/browser-runtime/protocol-exports.types.d.ts",
    ]
    result = subprocess.run(
        ["git", "check-attr", "eol", "--", *paths],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.splitlines() == [f"{path}: eol: lf" for path in paths]


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


def test_offline_module_bundle_is_deterministic_and_read_only(publisher):
    original = publisher._BUNDLE.read_bytes()
    assert publisher.bundle_bytes() == original
    assert publisher.bundle_bytes() == original
    assert publisher._BUNDLE.read_bytes() == original


def test_dependency_bridge_rejects_modified_vendor_bytes(publisher, tmp_path, monkeypatch):
    package = tmp_path / "tools/node_modules/elkjs"
    shutil.copytree(publisher._TOOLS / "node_modules/elkjs", package)
    bundle = package / "lib/elk.bundled.js"
    bundle.write_bytes(bundle.read_bytes() + b"\nwindow.Math = {};\n")
    monkeypatch.setattr(publisher, "_TOOLS", tmp_path / "tools")
    monkeypatch.setattr(publisher, "_ROOT", tmp_path)
    with pytest.raises(SystemExit, match="canonical vendored bundle"):
        publisher.prepare_dependencies()
    assert not (tmp_path / "node_modules/elkjs").exists()


def test_dependency_bridge_preserves_a_different_existing_install(publisher, tmp_path, monkeypatch):
    target = tmp_path / "node_modules/elkjs"
    target.mkdir(parents=True)
    marker = target / "package.json"
    marker.write_text('{"name":"elkjs","version":"other"}')
    before = marker.read_bytes()
    monkeypatch.setattr(publisher, "_ROOT", tmp_path)
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        publisher.prepare_dependencies()
    assert marker.read_bytes() == before
    assert list(target.iterdir()) == [marker]
