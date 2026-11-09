# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace
from typing import Any

import pytest
from test_delta import _model, _record

from archkeel.check.observation import _metrics
from archkeel.check.ratchets import RatchetError, measure_python_ratchets
from archkeel.ir import codec_observation
from archkeel.ir.codec import (
    delta_payload,
    observation_payload,
    parse_delta,
    parse_lock,
    parse_measurements,
    parse_observation,
    result_payload,
)
from archkeel.ir.facts import SourceSectionName
from archkeel.ir.lock import LockError, verify_observation
from archkeel.ir.measurements import Measurements, RatchetScalars, compare_measurements
from archkeel.ir.model import RunResult
from archkeel.ir.profiles import TYPESCRIPT, Profile
from archkeel.ir.structure import scope_metrics
from archkeel.render.html import _coverage, _structure_row, render_html


def _profile_model(analyzer: str) -> dict[str, Any]:
    model = _model(git_head="a" * 40)
    model["analyzer"]["name"] = analyzer
    if analyzer != "archkeel-python-analyzer":
        for key in (
            "calls_analyzed",
            "calls_resolved",
            "calls_partially_resolved",
            "calls_unresolved",
            "call_resolution_percent",
        ):
            model["coverage"][key] = None
    if analyzer == "archkeel-typescript-imports":
        for section in ("symbols", "references", "bindings"):
            model[section] = None
    if analyzer == "archkeel-dart-analyzer":
        for section in ("typing_signals", "constructs"):
            model[section] = None
    if analyzer == "archkeel-typescript-imports":
        for section in ("calls", "typing_signals", "constructs"):
            model[section] = None
    return model


def test_profile_codec_accepts_only_valid_nullable_call_groups() -> None:
    typescript = _profile_model("archkeel-typescript-imports")
    assert parse_observation(typescript).coverage.calls_analyzed is None

    malformed = deepcopy(typescript)
    malformed["coverage"]["calls_analyzed"] = 0
    with pytest.raises(ValueError, match="TypeScript call measurements must be null"):
        parse_observation(malformed)

    python = _profile_model("archkeel-python-analyzer")
    python["coverage"]["calls_analyzed"] = None
    with pytest.raises(ValueError, match="call measurements are required"):
        parse_observation(python)

    dart = _profile_model("archkeel-dart-analyzer")
    assert parse_observation(dart).coverage.calls_analyzed is None
    legacy_dart = deepcopy(dart)
    legacy_dart["coverage"].update(
        calls_analyzed=0,
        calls_resolved=0,
        calls_partially_resolved=0,
        calls_unresolved=0,
        call_resolution_percent=0.0,
    )
    assert parse_observation(legacy_dart).coverage.calls_analyzed == 0


def test_typescript_optional_sections_are_an_atomic_measurement_receipt() -> None:
    legacy = _profile_model("archkeel-typescript-imports")
    measured = deepcopy(legacy)
    for section in ("symbols", "calls", "references", "bindings"):
        measured[section] = []
    measured["coverage"].update(
        calls_analyzed=0,
        calls_resolved=0,
        calls_partially_resolved=0,
        calls_unresolved=0,
        call_resolution_percent=0.0,
    )
    observation = parse_observation(measured)
    assert observation.coverage.calls_analyzed == 0
    ratchets = measure_python_ratchets(observation)
    assert ratchets.calls_total is None
    assert ratchets.scalars.calls_unresolved is None

    mixed = deepcopy(measured)
    mixed["references"] = None
    with pytest.raises(ValueError, match="all null or all arrays"):
        parse_observation(mixed)


def test_legacy_typescript_inner_receipt_keeps_its_absent_construct_section() -> None:
    legacy = _profile_model("archkeel-typescript-imports")
    for section in ("symbols", "calls", "references", "bindings"):
        legacy[section] = []
    legacy["coverage"].update(
        calls_analyzed=0,
        calls_resolved=0,
        calls_partially_resolved=0,
        calls_unresolved=0,
        call_resolution_percent=0.0,
    )
    restored = parse_observation(legacy)
    replay = observation_payload(restored)
    assert replay["constructs"] is None
    assert all(replay[section] == [] for section in ("symbols", "calls", "references", "bindings"))
    assert parse_observation(replay) == restored


def test_typescript_construct_receipt_is_independent_of_the_inner_receipt() -> None:
    payload = _profile_model("archkeel-typescript-imports")
    payload["constructs"] = []
    restored = parse_observation(payload)
    replay = observation_payload(restored)
    assert replay["constructs"] == []
    assert all(
        replay[section] is None for section in ("symbols", "calls", "references", "bindings")
    )
    assert parse_observation(replay) == restored


def test_ratchets_skip_absent_typescript_sections_and_keep_python_validation() -> None:
    typescript = parse_observation(_profile_model("archkeel-typescript-imports"))
    result = measure_python_ratchets(typescript)
    assert result.scalars.typing_positions is None
    assert result.scalars.calls_unresolved is None
    assert result.calls_total is None
    assert result.resolution == "n/a"

    malformed_python = _profile_model("archkeel-python-analyzer")
    malformed_python["coverage"].update(
        calls_analyzed=2,
        calls_resolved=0,
        calls_partially_resolved=0,
        calls_unresolved=0,
    )
    with pytest.raises(RatchetError, match="calls_analyzed must equal"):
        measure_python_ratchets(parse_observation(malformed_python))


@pytest.mark.parametrize("total", [None, 0])
def test_absent_call_total_and_legacy_zero_decode_as_unmeasured(total: int | None) -> None:
    scalars = RatchetScalars(0, 0, None, None, None, 0, None)
    payload = {"scalars": asdict(scalars), "calls_total": total, "resolution": "n/a"}
    decoded = parse_measurements(payload, "unmeasured")
    assert decoded == Measurements(scalars, None, "n/a")
    assert asdict(decoded)["calls_total"] is None
    rows = compare_measurements(decoded, decoded)
    assert next(row for row in rows if row[0] == "calls_unresolved")[3] == "n/a"
    assert next(row for row in rows if row[0] == "unresolved_ratio") == (
        "unresolved_ratio",
        "n/a/n/a",
        "n/a/n/a",
        "n/a",
    )


@pytest.mark.parametrize(
    ("total", "unresolved", "resolution"),
    [
        (None, 0, "n/a"),
        (None, None, "measured"),
        (1, None, "measured"),
        (0, 0, "measured"),
        (1, 0, "n/a"),
        (1, 2, "measured"),
        (True, 0, "measured"),
        (-1, 0, "measured"),
        (1.0, 0, "measured"),
        ("1", 0, "measured"),
    ],
)
def test_incoherent_or_malformed_call_measurements_are_rejected(
    total: object, unresolved: int | None, resolution: str
) -> None:
    scalars = asdict(RatchetScalars(0, 0, 0, 0, unresolved, 0))
    with pytest.raises(RatchetError):
        parse_measurements(
            {"scalars": scalars, "calls_total": total, "resolution": resolution}, "invalid"
        )


@pytest.mark.parametrize(("total", "unresolved"), [(None, 0), (0, None), (1, None)])
def test_typed_call_count_availability_must_agree(
    total: int | None, unresolved: int | None
) -> None:
    with pytest.raises(RatchetError):
        Measurements(RatchetScalars(0, 0, 0, 0, unresolved, 0), total, "n/a")


@pytest.mark.parametrize(("version", "total"), [("1.0.0", 0), ("2.0.0", None)])
def test_unmeasured_accepted_lock_versions_preserve_legacy_reads(
    version: str, total: int | None
) -> None:
    from test_git_lock import _lock

    raw = json.loads(_lock(_profile_model("archkeel-python-analyzer")))
    fresh = measure_python_ratchets(parse_observation(_profile_model("archkeel-dart-analyzer")))
    raw["schema_version"] = version
    raw["measurements"] = asdict(fresh)
    raw["measurements"]["calls_total"] = total
    lock = parse_lock(json.dumps(raw).encode())
    assert lock.measurements == fresh
    verify_observation(lock, observation_digest=lock.observation_digest, measurements=fresh)
    measured_zero = measure_python_ratchets(
        parse_observation(_profile_model("archkeel-python-analyzer"))
    )
    with pytest.raises(LockError, match="differs"):
        verify_observation(
            lock, observation_digest=lock.observation_digest, measurements=measured_zero
        )
    if version == "1.0.0":
        raw["measurements"]["calls_total"] = None
        with pytest.raises(LockError, match="null call totals"):
            parse_lock(json.dumps(raw).encode())


@pytest.mark.parametrize("version", ["1.2.0", "1.3.0", "1.4.0", "2.0.0"])
def test_only_profile_delta_version_accepts_fresh_null_call_totals(version: str) -> None:
    from test_expectation import _delta_payload

    raw = _delta_payload()
    raw["schema_version"] = version
    for side in ("baseline", "head"):
        raw["ratchets"][side]["scalars"]["calls_unresolved"] = None
    parsed = parse_delta(raw)
    assert parsed.ratchets.head.calls_total is None
    emitted = delta_payload(parsed)
    assert emitted["ratchets"]["head"]["calls_total"] == (
        None if version in {"1.4.0", "2.0.0"} else 0
    )
    assert parse_delta(emitted) == parsed
    assert result_payload(RunResult("check", 0, delta=parsed))["delta"] == emitted
    for side in ("baseline", "head"):
        raw["ratchets"][side]["calls_total"] = None
    if version in {"1.4.0", "2.0.0"}:
        assert parse_delta(raw).ratchets.head.calls_total is None
    else:
        with pytest.raises(RatchetError, match="null call totals"):
            parse_delta(raw)


def test_structure_and_coverage_render_n_a_for_unmeasured_calls() -> None:
    observation = parse_observation(_profile_model("archkeel-typescript-imports"))
    metric = scope_metrics(observation, "package", {})[0:]
    assert metric == ()
    metric = scope_metrics(observation, "package", {"pkg.a": "pkg"})[0]
    assert metric.calls is None
    assert metric.unresolved is None
    assert "n/a" in _structure_row(metric)

    rendered = _coverage(observation)
    assert "n/a" in rendered
    assert "None" not in rendered
    page = render_html(
        RunResult("report", 0, observation=observation),
        observation,
        repository="sample",
        architecture_href=None,
    ).decode()
    assert "Call resolution is not measured." in page
    assert "None of None calls unresolved" not in page

    python = parse_observation(_profile_model("archkeel-python-analyzer"))
    python_metric = scope_metrics(python, "package", {"pkg.module": "pkg"})[0]
    assert python_metric.calls == 0
    assert python_metric.unresolved == 0


def test_forbidden_package_edges_use_declared_module_packages() -> None:
    source_module = "@scope/library/src/long/path"
    target_module = "@other/dependency/src/deep/module"
    scan = SimpleNamespace(
        violations=[
            _record(
                "vio",
                kind="forbidden_dependency",
                data={"source_module": source_module, "target_module": target_module},
            ),
            _record(
                "vio-external",
                kind="forbidden_dependency",
                data={"source_module": source_module, "target_module": "react"},
            ),
        ],
        imports=[
            _record(
                "imp",
                kind="import",
                data={
                    "source_module": source_module,
                    "target_module": target_module,
                    "source_package": "@scope/library",
                    "target_package": "@other/dependency",
                    "symbol": "value",
                },
            ),
            _record(
                "imp-external",
                kind="import",
                data={
                    "source_module": source_module,
                    "target_module": "react",
                    "source_package": "@scope/library",
                    "target_package": "react",
                    "symbol": "useState",
                },
            ),
        ],
        unknowns=[],
        cycles=[],
        calls=[],
        evidence=[],
        modules=[
            _record(
                "mod-a",
                kind="module",
                data={"qualified_name": source_module, "package": "@scope/library"},
            ),
            _record(
                "mod-b",
                kind="module",
                data={"qualified_name": target_module, "package": "@other/dependency"},
            ),
        ],
        packages=[],
        symbols=[],
        typing_signals=[],
        coverage={
            "files_discovered": 2,
            "ast_coverage_percent": 100,
            "call_resolution_percent": None,
        },
        observed_sections=frozenset(),
        dependency_edges=[
            _record(
                "pkg-edge",
                kind="dependency_edge",
                data={
                    "level": "package",
                    "source": "@scope/library",
                    "target": "@other/dependency",
                },
            ),
            _record(
                "pkg-edge-external",
                kind="dependency_edge",
                data={"level": "package", "source": "@scope/library", "target": "react"},
            ),
        ],
    )
    contract = SimpleNamespace(component_for=lambda _module: None)

    metrics = _metrics(scan, contract, profile=TYPESCRIPT)

    edge_count = next(
        item["data"]["value"] for item in metrics if item["kind"] == "forbidden_package_edges"
    )
    assert edge_count == 2
    by_kind = {item["kind"]: item for item in metrics}
    assert by_kind["symbols"]["data"]["value"] is None
    assert by_kind["private_crossings"]["data"]["value"] is None
    assert by_kind["untyped_private_accesses"]["data"]["value"] is None
    assert by_kind["typing_signals"]["data"]["value"] is None
    assert by_kind["unresolved_calls"]["data"]["value"] is None
    assert by_kind["call_resolution"]["data"]["value"] is None


_LEGACY_TYPESCRIPT_OPTIONAL = frozenset(
    {
        SourceSectionName.SYMBOLS,
        SourceSectionName.CALLS,
        SourceSectionName.REFERENCES,
        SourceSectionName.BINDINGS,
    }
)


def _consume_profile_receipts(monkeypatch, profile):
    # Inject a real Profile at the existing codec seam; source authority is not under test.
    monkeypatch.setattr(codec_observation, "profile_for", lambda _analyzer: profile)
    payload = _profile_model(TYPESCRIPT.analyzer)
    sections = (*_LEGACY_TYPESCRIPT_OPTIONAL, SourceSectionName.CONSTRUCTS)
    for section in sections:
        payload[section] = []
    for section in profile.all_optional_sections | profile.absent_sections:
        payload[section] = None
    if payload["calls"] is not None:
        payload["coverage"].update(
            calls_analyzed=0,
            calls_resolved=0,
            calls_partially_resolved=0,
            calls_unresolved=0,
            call_resolution_percent=0.0,
        )
    restored = parse_observation(payload)
    replay = observation_payload(restored)
    assert all(replay[section] == payload[section] for section in sections)
    assert parse_observation(replay) == restored


@pytest.mark.parametrize("construction", ["keyword", "positional"])
def test_legacy_profile_constructor_keeps_its_atomic_group_and_codec(monkeypatch, construction):
    legacy = _LEGACY_TYPESCRIPT_OPTIONAL
    if construction == "keyword":
        profile = Profile(
            analyzer=TYPESCRIPT.analyzer,
            source_suffix=".ts",
            absent_sections=TYPESCRIPT.absent_sections,
            optional_sections=legacy,
            standard_library=frozenset({"stdlib"}),
            sdk_libraries=frozenset({"sdk"}),
            module_object_imports=True,
            crate_edges_only=False,
        )
    else:
        # Exact old positional order, including the three fields after optional_sections.
        profile = Profile(
            TYPESCRIPT.analyzer,
            ".ts",
            frozenset(),
            True,
            True,
            False,
            False,
            frozenset(),
            frozenset(),
            TYPESCRIPT.absent_sections,
            legacy,
            frozenset({"stdlib"}),
            frozenset({"sdk"}),
            True,
            crate_edges_only=False,
        )
    assert profile.optional_sections == legacy
    assert profile.optional_section_groups == (legacy,)
    assert profile.all_optional_sections == legacy
    assert profile.standard_library == frozenset({"stdlib"})
    assert profile.sdk_libraries == frozenset({"sdk"}) and profile.module_object_imports
    _consume_profile_receipts(monkeypatch, profile)


@pytest.mark.parametrize(
    "legacy",
    [frozenset({SourceSectionName.SYMBOLS}), frozenset()],
    ids=["changed-legacy-group", "emptied-legacy-group"],
)
def test_profile_replace_changes_only_the_legacy_group(monkeypatch, legacy):
    profile = replace(TYPESCRIPT, optional_sections=legacy)
    additional = (frozenset({SourceSectionName.CONSTRUCTS}),)
    assert profile.optional_sections == legacy
    assert profile.additional_optional_section_groups == additional
    assert profile.optional_section_groups == ((legacy,) if legacy else ()) + additional
    assert profile.all_optional_sections == legacy | additional[0]
    _consume_profile_receipts(monkeypatch, profile)


def test_unrelated_profile_replace_preserves_legacy_and_additional_receipts(monkeypatch):
    profile = replace(TYPESCRIPT, source_suffix=".jsx")
    assert profile.optional_sections == _LEGACY_TYPESCRIPT_OPTIONAL
    assert profile.additional_optional_section_groups == (
        frozenset({SourceSectionName.CONSTRUCTS}),
    )
    assert profile.optional_section_groups == (
        _LEGACY_TYPESCRIPT_OPTIONAL,
        frozenset({SourceSectionName.CONSTRUCTS}),
    )
    _consume_profile_receipts(monkeypatch, profile)


def test_additional_profile_groups_are_keyword_only():
    from inspect import Parameter, signature

    assert (
        signature(Profile).parameters["additional_optional_section_groups"].kind
        is Parameter.KEYWORD_ONLY
    )


@pytest.mark.parametrize(
    "groups",
    [
        (frozenset({SourceSectionName.SYMBOLS}),),
        (frozenset({SourceSectionName.CONSTRUCTS}),) * 2,
        (frozenset(),),
    ],
    ids=["overlaps-legacy", "overlaps-additional", "empty-additional"],
)
def test_additional_profile_groups_are_nonempty_and_disjoint(groups):
    with pytest.raises(ValueError, match="non-empty and disjoint"):
        replace(TYPESCRIPT, additional_optional_section_groups=groups)
