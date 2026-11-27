# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-418, AD-432: a violation planted in a copy of `native/` fails its self-contract rule (#880).

`make self-validate-native` decides the unmodified checkout; these tests plant a module cycle.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from core_support import ROOT, run
from frozen_native import frozen_root as frozen_root
from rustc_dev_support import needs_rustc_dev

from archkeel.cli import core_only

sys.path.insert(0, str(ROOT / "tools"))


def test_a_planted_report_cycle_fails_the_native_component_rule(
    tmp_path: Path, frozen_root: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = shutil.copytree(frozen_root, tmp_path / "planted")
    renderer = root / "native/report/src/html.rs"
    with renderer.open("a", encoding="utf-8") as source:
        source.write(
            "\n#[allow(dead_code)]\n"
            "fn planted_return(frame: &Map<String, Value>) -> Result<Value, serde_json::Error> {\n"
            "    crate::engine_frame::page(frame)\n"
            "}\n"
        )
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    code, result = run("validate", "--root", str(root), "--config", "native/archkeel.toml")
    frame = result["frame"]
    rule = "NATIVE-NO-COMPONENT-CYCLES"
    assert (code, frame["rules"][rule][1]) == (1, "FAIL")
    [cycle] = frame["explain"]["cycles"][rule]["items"]
    assert {(step["from"], step["to"]) for step in cycle["path"]} == {
        ("report-frame", "report-page"),
        ("report-page", "report-frame"),
    }
    assert all(step["evidence"] and not step.get("possible") for step in cycle["path"])


@needs_rustc_dev
def test_routing_the_body_walk_through_params_restores_the_module_cycle(
    tmp_path: Path, frozen_root: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = shutil.copytree(frozen_root, tmp_path / "planted")
    rust = root / "native/rust/src"
    orchestration = rust / "scan_receivers.rs"
    text = orchestration.read_text(encoding="utf-8")
    call = "bodies::extend(block, &mut params, &bound);"
    assert text.count(call) == 1
    orchestration.write_text(
        text.replace(call, "params::extend_body(block, &mut params, &bound);"), encoding="utf-8"
    )
    with (rust / "scan_params.rs").open("a", encoding="utf-8") as source:
        source.write(
            "\npub(super) fn extend_body("
            "block: &syn::Block, params: &mut Params, bound: &Bound) {\n"
            "    super::bodies::extend(block, params, bound);\n"
            "}\n"
        )
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    code, result = run("validate", "--root", str(root), "--config", "native/archkeel.toml")
    frame = result["frame"]
    rule = "NATIVE-NO-MODULE-CYCLES"
    assert (code, frame["rules"][rule][1]) == (1, "FAIL")
    assert frame["rules"]["NATIVE-NO-COMPONENT-CYCLES"][1] == "PASS"
    prefix = "native.archkeel_rust_collector.scan.receivers."
    [cycle] = frame["explain"]["cycles"][rule]["items"]
    assert {(step["from"], step["to"]) for step in cycle["path"]} == {
        (prefix + "bodies", prefix + "params"),
        (prefix + "params", prefix + "bodies"),
    }
    assert all(step["evidence"] and not step.get("possible") for step in cycle["path"])


def test_a_facts_data_dependency_on_sections_fails_the_native_module_rule(
    tmp_path: Path, frozen_root: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = shutil.copytree(frozen_root, tmp_path / "planted")
    with (root / "native/facts/src/data/mod.rs").open("a", encoding="utf-8") as source:
        source.write(
            "\n#[allow(dead_code)]\n"
            "fn planted_gap(fact: crate::sections::GapFact) -> crate::sections::GapFact {\n"
            "    fact\n"
            "}\n"
        )
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    code, result = run("validate", "--root", str(root), "--config", "native/archkeel.toml")
    frame = result["frame"]
    rule = "NATIVE-NO-MODULE-CYCLES"
    assert (code, frame["rules"][rule][1]) == (1, "FAIL")
    data, sections = "native.archkeel_facts.data", "native.archkeel_facts.sections"
    [cycle] = frame["explain"]["cycles"][rule]["items"]
    assert {(step["from"], step["to"]) for step in cycle["path"]} == {
        (data, sections),
        (sections, data),
    }
    assert all(step["evidence"] and not step.get("possible") for step in cycle["path"])


@needs_rustc_dev
def test_a_globals_return_edge_fails_the_native_module_rule(
    tmp_path: Path, frozen_root: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = shutil.copytree(frozen_root, tmp_path / "planted")
    with (root / "native/python/src/survey/globals_uses.rs").open("a", encoding="utf-8") as source:
        source.write(
            "\n#[allow(dead_code)]\n"
            "fn planted_read(modules: &[crate::module::Module]) {\n"
            "    drop(super::globals_read::inert_reads(modules));\n"
            "}\n"
        )
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    code, result = run("validate", "--root", str(root), "--config", "native/archkeel.toml")
    frame = result["frame"]
    rule = "NATIVE-NO-MODULE-CYCLES"
    assert (code, frame["rules"][rule][1]) == (1, "FAIL")
    assert frame["rules"]["NATIVE-NO-COMPONENT-CYCLES"][1] == "PASS"
    prefix = "native.archkeel_python_collector.survey."
    read, uses = prefix + "globals_read", prefix + "globals_uses"
    [cycle] = frame["explain"]["cycles"][rule]["items"]
    assert {(step["from"], step["to"]) for step in cycle["path"]} == {(read, uses), (uses, read)}
    assert all(step["evidence"] and not step.get("possible") for step in cycle["path"])
