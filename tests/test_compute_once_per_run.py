# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One report command computes each per-run result once (epic #880, task D1).

Each count is the number of real computations in one `archkeel report` of a small TypeScript
project. A count that rises again means a stage repeats work of an earlier stage.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import replace
from importlib import import_module
from pathlib import Path

import pytest
from native_typescript import trusted
from test_partial_member_inventory import _Collector, _project

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report_with_observation
from archkeel.cli import main
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.dependency_binding import replayed_dependency_binding_id
from archkeel.ir.member_inventory import validated_member_inventory_proof


def _count(monkeypatch: pytest.MonkeyPatch, module: str, name: str) -> list[int]:
    """Count calls of one function in every archkeel module that holds it."""
    original = getattr(import_module(module), name)
    calls: list[int] = []

    def counted(*args: object, **kwargs: object) -> object:
        calls.append(1)
        return original(*args, **kwargs)

    for loaded in list(sys.modules.values()):
        if loaded.__name__.startswith("archkeel") and getattr(loaded, name, None) is original:
            monkeypatch.setattr(loaded, name, counted)
    return calls


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("once")
    _project(root, "typescript")
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["src"]\nnamespace = "demo"\nlanguage = "typescript"\n'
        'contract = "architecture-contract.json"\n'
    )
    return root


@pytest.fixture(scope="module")
def report_counts(project: Path) -> dict[str, int]:
    root = project
    patch = pytest.MonkeyPatch()
    watched = {
        "inventory_binding": ("archkeel.ir.member_inventory", "_inventory_binding"),
        "dependency_binding": ("archkeel.ir.dependency_binding", "dependency_binding_id"),
        "report_build": ("archkeel.ir.report_graph", "_build_architecture_report"),
        "report_decode": ("archkeel.ir.codec_observation", "decode_canonical_model"),
        "tree_load": ("archkeel.ir.codec_inside", "load_inside_contract_tree"),
        "contract_parse": ("archkeel.ir.codec_contract", "parse_contract"),
    }
    calls = {key: _count(patch, *target) for key, target in watched.items()}
    try:
        patch.setattr(
            "archkeel.cli.observer_for", lambda *a, **k: trusted(_Collector("typescript"))
        )
        main(["report", "--root", str(root), "--output", str(root / "out" / "architecture.json")])
    finally:
        patch.undo()
    return {key: len(value) for key, value in calls.items()}


def test_the_inventory_binding_is_computed_once_for_each_observation_object(report_counts) -> None:
    # Issue, then one replay for each of the three observation objects the UML phases build.
    # Before this change the same report computed it 10 times.
    assert report_counts["inventory_binding"] == 4


def test_the_dependency_binding_is_computed_once_per_flag_set(report_counts) -> None:
    # This project replays one flag set. The `nest-realworld-project` demo replays two (13 before).
    assert report_counts["dependency_binding"] == 1


def test_the_architecture_report_is_built_once(report_counts) -> None:
    assert report_counts["report_build"] == 1


def test_the_report_command_does_not_decode_its_own_output(report_counts) -> None:
    assert report_counts["report_decode"] == 0


def test_observe_and_assemble_share_one_contract_read(report_counts) -> None:
    # The second read is the UML phase: it checks the contract on disk against the observed one.
    assert report_counts["tree_load"] == 2
    assert report_counts["contract_parse"] == 2


def test_the_package_digest_is_a_process_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    from archkeel.ir import digest

    digest.package_digest.cache_clear()
    reads: list[Path] = []
    original: Callable[[Path], bytes] = Path.read_bytes

    def counted(self: Path) -> bytes:
        reads.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", counted)
    assert digest.package_digest() == digest.package_digest()
    assert len(reads) == len({*reads})


def test_a_page_asset_is_read_once() -> None:
    from archkeel.render.page_assets import asset, data_uri

    assert asset("flow.js") is asset("flow.js")
    assert data_uri("archkeel-mark.svg", "image/svg+xml") is data_uri(
        "archkeel-mark.svg", "image/svg+xml"
    )


def test_a_replayed_dependency_binding_is_kept_for_its_object_and_flag_set(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = ScanConfig(
        ("src",), "demo", "architecture-contract.json", "unused", language="typescript"
    )
    _, _, observation = run_report_with_observation(
        project, config=config, analyzer=trusted(_Collector("typescript"))
    )
    assert observation is not None
    computed = _count(monkeypatch, "archkeel.ir.dependency_binding", "dependency_binding_id")
    first = replayed_dependency_binding_id(observation)
    assert [replayed_dependency_binding_id(observation) for _ in range(3)] == [first] * 3
    assert len(computed) == 1
    replayed_dependency_binding_id(observation, include_calls=True)
    assert len(computed) == 2
    assert replayed_dependency_binding_id(replace(observation)) == first
    assert len(computed) == 3


def test_a_decoded_observation_replays_the_member_inventory_proof_again(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AD-229: a saved observation is another object, so the memo does not serve it."""
    config = ScanConfig(
        ("src",), "demo", "architecture-contract.json", "unused", language="typescript"
    )
    _, _, live = run_report_with_observation(
        project, config=config, analyzer=trusted(_Collector("typescript"))
    )
    assert live is not None
    proof = validated_member_inventory_proof(live)
    assert proof is not None
    replays = _count(monkeypatch, "archkeel.ir.member_inventory", "_replay_member_inventory_proof")
    assert validated_member_inventory_proof(live) is proof
    assert not replays
    saved = parse_observation(decode_canonical_model(json.loads(canonical_report_bytes(live))))
    assert saved is not live
    assert validated_member_inventory_proof(saved) == proof
    assert len(replays) == 1
