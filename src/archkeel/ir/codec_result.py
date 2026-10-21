# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Serialize command results and filtered architecture views."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace

from archkeel.ir.architecture_projection import ArchitectureProjection
from archkeel.ir.codec_contract import _rule_payload
from archkeel.ir.codec_delta import delta_payload
from archkeel.ir.codec_observation import _coverage_payload, observation_payload
from archkeel.ir.codec_wire import _raw_object, canonical_json_bytes
from archkeel.ir.command_view import ArchitectureComponentView, architecture_command_envelope
from archkeel.ir.facts_codec import record_payload as _record_payload
from archkeel.ir.model import Command as _Command
from archkeel.ir.model import FilteredViolation, OpenDecision, ReportFilter, RunResult
from archkeel.ir.model import RawJson as RawJson


def _open_decision_payload(decision: OpenDecision) -> dict[str, RawJson]:
    payload: dict[str, RawJson] = {
        "source": decision.source,
        "target": decision.target,
        "observed": decision.observed,
        "import_sites": decision.import_sites,
    }
    if decision.options_unavailable_reason is None:
        if (
            decision.source_package is None
            or decision.target_package is None
            or decision.allowed_option is None
            or decision.forbidden_option is None
        ):
            raise ValueError("package open decision is missing its package-rule options")
        payload.update(
            source_package=decision.source_package,
            target_package=decision.target_package,
            options={
                "allowed_dependency": _rule_payload(decision.allowed_option),
                "forbidden_dependency": _rule_payload(decision.forbidden_option),
            },
        )
    else:
        payload.update(
            source_packages=list(decision.source_packages),
            target_packages=list(decision.target_packages),
            source_exact_modules=list(decision.source_exact_modules),
            target_exact_modules=list(decision.target_exact_modules),
            options={},
            options_unavailable_reason=decision.options_unavailable_reason,
        )
        if decision.source_package is not None:
            payload["source_package"] = decision.source_package
        if decision.target_package is not None:
            payload["target_package"] = decision.target_package
    return payload


def _architecture_component_payload(
    component: ArchitectureComponentView,
    *,
    compact: bool = False,
    summary: bool = False,
) -> dict[str, RawJson]:
    if compact:
        component = replace(
            component,
            path=None,
            provenance=(),
            modules={},
            used_by={},
            exact_modules=(),
            finding_ids=(),
            requires=tuple(
                replace(item, through=(), observed_imports=None) for item in component.requires
            ),
            permissions=tuple(replace(item, rule_ids=()) for item in component.permissions),
        )
    row = _raw_object(asdict(component))
    for name in ("parent_id", "namespace", "selector_prefix", "layer", "public", "planned"):
        if row[name] is None:
            del row[name]
    for name in (
        "exact_modules",
        "modules",
        "requires",
        "permissions",
        "used_by",
        "finding_ids",
    ):
        if row[name] == [] or row[name] == {}:
            del row[name]
    if row["role"] == "component":
        del row["role"]
    permission_rows: list[dict[str, RawJson]] = []
    for permission in component.permissions:
        if compact:
            permission_rows.append(
                {"status": permission.status, "target_ids": list(permission.target_ids)}
            )
        else:
            item = _raw_object(asdict(permission))
            if item["rule_ids"] == []:
                del item["rule_ids"]
            permission_rows.append(item)
    if permission_rows:
        row["permissions"] = permission_rows
    if summary:
        for name in (
            "path",
            "provenance",
            "packages",
            "namespace",
            "selector_prefix",
            "exact_modules",
            "public",
            "planned",
            "modules",
            "requires",
            "permissions",
            "used_by",
            "finding_ids",
        ):
            if name in row:
                del row[name]
    return row


def _architecture_result_payload(result: RunResult) -> dict[str, RawJson]:
    envelope = architecture_command_envelope(result)
    payload = _raw_object(asdict(replace(envelope, filtered_violations=(), recorded_unknowns=None)))
    if result.report_filter is not None:
        payload["report_filter"] = _report_filter_payload(result.report_filter)
    full_architecture = bool(result.report_filter and result.report_filter.full_architecture)
    projection_view = envelope.architecture_projection
    projection = _raw_object(asdict(projection_view))
    component_selected = bool(result.report_filter and result.report_filter.component)
    projection["components"] = [
        {
            **_architecture_component_payload(
                component,
                compact=not full_architecture,
                summary=(
                    not full_architecture
                    and not component_selected
                    and component.parent_id is not None
                ),
            ),
            **({"finding_count": len(component.finding_ids)} if not full_architecture else {}),
        }
        for component in projection_view.components
    ]
    projection["permission_rules"] = [
        {
            "declaration": _record_payload(rule.declaration),
            "assessment": _raw_object(asdict(rule.assessment))
            if rule.assessment is not None
            else None,
            **({"parent_id": rule.parent_id} if rule.parent_id is not None else {}),
        }
        for rule in envelope.architecture_projection.permission_rules
    ]
    if not full_architecture:
        del projection["permission_rules"]
        del projection["policy_context"]
    payload["architecture_projection"] = projection
    if result.coverage is not None:
        payload["coverage"] = _coverage_payload(result.coverage)
    payload["diagnostics"] = [
        {
            key: value
            for key, value in _raw_object(asdict(item)).items()
            if (key not in {"pointer", "code", "contract_path"} or value is not None)
            and (key != "locations" or value)
        }
        for item in result.diagnostics
    ]
    rows = result.filtered_violations
    payload["filtered_violation_count"] = len(rows) if rows is not None else None
    payload["violation_details_included"] = full_architecture and rows is not None
    if full_architecture:
        payload["recorded_unknowns"] = (
            [_record_payload(record) for record in envelope.recorded_unknowns]
            if envelope.recorded_unknowns is not None
            else None
        )
        if rows is None:
            payload["filtered_violations"] = None
        else:
            component_scopes, gaps, remedy = _violation_context(result.architecture_projection)
            payload["filtered_violations"] = [
                _filtered_violation_payload(item, component_scopes, gaps, remedy) for item in rows
            ]
    else:
        del payload["filtered_violations"]
        del payload["recorded_unknowns"]
    for name in ("baseline_path", "baseline_comparisons", "baseline_new", "baseline_resolved"):
        if payload[name] is None:
            del payload[name]
    return payload


def _violation_context(
    projection: ArchitectureProjection | None,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]], str | None]:
    if projection is None:
        return {}, {}, None
    return (
        {item.id: item.scope for item in projection.components},
        {item.module: item.candidate_ids for item in projection.ownership_gaps},
        projection.violation_remedy,
    )


def _filtered_violation_payload(
    item: FilteredViolation,
    component_scopes: Mapping[str, str],
    gaps: Mapping[str, tuple[str, ...]],
    remedy: str | None,
) -> dict[str, RawJson]:
    row: dict[str, RawJson] = {
        **_record_payload(item.record),
        "locations": [_raw_object(asdict(location)) for location in item.locations],
    }
    if item.record.kind == "complete_assignment" and remedy is not None:
        module = item.record.data.get("module")
        owner_ids = gaps.get(module, ()) if isinstance(module, str) else ()
        row["owners"] = [component_scopes.get(identity, identity) for identity in owner_ids] or [
            "none"
        ]
        row["remedy"] = remedy
    return row


def result_payload(result: RunResult) -> dict[str, RawJson]:
    if (
        result.command is _Command.REPORT
        and result.report_filter is not None
        and result.report_filter.only_architecture
        and result.architecture_projection is not None
    ):
        return _architecture_result_payload(result)
    payload = _raw_object(asdict(replace(result, architecture_projection=None)))
    if result.contract_changes is None:
        # AD-255: absent without --against, so every other result keeps its 9.0 shape.
        del payload["contract_changes"]
    if result.report_filter is not None:
        payload["report_filter"] = _report_filter_payload(result.report_filter)
    if result.provenance is not None and result.provenance.initial_pr is None:
        provenance = _raw_object(asdict(result.provenance))
        del provenance["initial_pr"]
        payload["provenance"] = provenance
    payload["diagnostics"] = [
        {
            key: value
            for key, value in _raw_object(asdict(diagnostic)).items()
            if (key not in {"pointer", "code", "contract_path"} or value is not None)
            and (key != "locations" or value)
        }
        for diagnostic in result.diagnostics
    ]
    payload["open_decisions"] = [
        _open_decision_payload(decision) for decision in result.open_decisions
    ]
    if result.filtered_violations is not None:
        component_scopes, gaps, remedy = _violation_context(result.architecture_projection)
        payload["filtered_violations"] = [
            _filtered_violation_payload(item, component_scopes, gaps, remedy)
            for item in result.filtered_violations
        ]
    if result.observation is not None:
        payload["observation"] = observation_payload(result.observation)
    if result.coverage is not None:
        payload["coverage"] = _coverage_payload(result.coverage)
    if result.delta is not None:
        payload["delta"] = delta_payload(result.delta)
    return payload


def _report_filter_payload(report_filter: ReportFilter) -> dict[str, RawJson]:
    payload: dict[str, RawJson] = {
        "only_violations": report_filter.only_violations,
        "rule": report_filter.rule,
        "component": report_filter.component,
        "only_calls": report_filter.only_calls,
        "only_architecture": report_filter.only_architecture,
    }
    if report_filter.full_architecture:
        payload["full_architecture"] = True
    return payload


def result_bytes(result: RunResult) -> bytes:
    return canonical_json_bytes(result_payload(result))
