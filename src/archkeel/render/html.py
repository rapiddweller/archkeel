# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Render a portable evidence report without changing check semantics."""

from __future__ import annotations

import base64
import html
import json
import re
from dataclasses import replace
from importlib.resources import files
from typing import TypeAlias

from archkeel.ir.bindings import BindingReads, unread_bindings
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import agent_decisions, open_decisions
from archkeel.ir.duplication import MINIMUM_SHAPE_NODES, OwnedLogic, repeated_logic
from archkeel.ir.interfaces import (
    InterfaceEdge,
    InterfaceName,
    component_owners,
    interface_edges,
    interface_profile,
    owner_of,
)
from archkeel.ir.levels import inside_levels
from archkeel.ir.measurements import Measurements
from archkeel.ir.model import (
    BaselineViolationComparison,
    CallRow,
    Diagnostic,
    Observation,
    Record,
    RecordData,
    RuleAssessment,
    RunResult,
    in_scope,
)
from archkeel.ir.references import SymbolReferences, unreferenced_symbols
from archkeel.ir.structure import (
    InsideSizes,
    StructureMetric,
    oversized_insides,
    structure_metrics,
)
from archkeel.ir.type_fanin import MINIMUM_CROSSINGS, TypeFanin, type_fanin

from .flow import FlowComponent, FlowData, FlowEdge, FlowInnerEdge, FlowInside, build_flow
from .summary import (
    Comparison,
    VerdictRow,
    badge,
    check_summary,
    report_summary,
    report_violates_rules,
)


def _asset(name: str) -> bytes:
    return files("archkeel.render").joinpath("assets", name).read_bytes()


def _data_uri(name: str, mime_type: str) -> str:
    encoded = base64.b64encode(_asset(name)).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _text(value: object) -> str:
    return html.escape(str(value), quote=True)


def _verdict_card(row: VerdictRow) -> str:
    state = badge(row.value)
    return f"""
      <article class="verdict-card" data-verdict="{state.state}">
        <div class="verdict-state"><span aria-hidden="true">{state.symbol}</span>{state.label}</div>
        <h3>{_text(row.label)}</h3>
        <code class="verdict-key">{_text(row.key)}</code>
        <p>{_text(row.reason)}</p>
      </article>"""


def _document(*, repository: str, kind: str, title: str, content: str) -> bytes:
    css = _asset("archkeel-report.css").decode("utf-8")
    dark_logo = _data_uri("archkeel-logo-dark.svg", "image/svg+xml")
    light_logo = _data_uri("archkeel-logo-light.svg", "image/svg+xml")
    mark = _data_uri("archkeel-mark.svg", "image/svg+xml")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; img-src data:; style-src 'unsafe-inline';
                 script-src 'unsafe-inline'">
  <link rel="icon" href="{mark}" type="image/svg+xml">
  <title>{_text(title)} · {_text(repository)}</title>
  <style>{css}</style>
</head>
<body>
  <header class="report-header">
    <img class="report-logo report-logo-dark" src="{dark_logo}" alt="Archkeel">
    <img class="report-logo report-logo-light" src="{light_logo}" alt="Archkeel">
    <span class="report-kind">{_text(kind)}</span>
  </header>
  <main class="report-shell">
    {content}
    <footer class="report-footer">Archkeel · deterministic architecture evidence</footer>
  </main>
</body>
</html>
""".encode()


def _diagnostic(item: Diagnostic) -> str:
    fields = [
        ("kind", item.kind),
        ("subject", item.subject),
        ("unknown_claim", item.unknown_claim),
        ("remedy", item.remedy),
    ]
    if item.code is not None:
        fields.append(("code", item.code))
    values = "".join(f"<dt>{name}</dt><dd>{_text(value)}</dd>" for name, value in fields)
    return f'<dl class="diagnostic">{values}</dl>'


def _record_row(item: Record, observation: Observation) -> str:
    evidence = {entry.id: entry for entry in observation.evidence}
    location = ""
    if item.evidence_ids:
        source = evidence.get(item.evidence_ids[0])
        if source is not None:
            # AD-107: line 0 cites the whole file, which has no line to name.
            location = f"{source.file}:{source.line}" if source.line else source.file
    subjects = " · ".join(item.subjects)
    return (
        "<tr>"
        f"<td><code>{_text(item.id)}</code></td>"
        f"<td>{_text(item.title)}</td>"
        f"<td><code>{_text(subjects)}</code></td>"
        f"<td><code>{_text(location)}</code></td>"
        "</tr>"
    )


def _findings(title: str, items: tuple[Record, ...], observation: Observation) -> str:
    if not items:
        return f'<section class="report-section"><h2>{_text(title)}</h2><p>None.</p></section>'
    rows = "".join(_record_row(item, observation) for item in items)
    return f"""
    <section class="report-section">
      <h2>{_text(title)} · {len(items)}</h2>
      <p>Recorded analysis limits, not declared-rule violations.</p>
      <details class="report-evidence"><summary>Inspect all {len(items)} records</summary>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Fingerprint</th><th>Finding</th><th>Subjects</th><th>Evidence</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div></details>
    </section>"""


def _violations(
    items: tuple[Record, ...],
    observation: Observation,
    baseline: tuple[BaselineViolationComparison, ...] | None = None,
) -> str:
    """Render a local violations-only view without changing the CLI-selected records."""
    if not items:
        return (
            '<section class="report-section"><h2>Declared-rule violations</h2>'
            "<p>None.</p></section>"
        )
    comparisons = tuple(baseline or ())
    grouped: dict[tuple[str, ...], list[Record]] = {}
    for item in items:
        grouped.setdefault(tuple(sorted(item.rule_ids)), []).append(item)
    rows = "".join(
        _violation_group(rule_ids, grouped[rule_ids], observation, comparisons)
        for rule_ids in sorted(grouped)
    )
    script = _asset("violations.js").decode("utf-8")
    return f"""
    <section class="report-section" aria-labelledby="violations-heading">
      <h2 id="violations-heading">Declared-rule violations</h2>
      <div class="violation-focus" data-violation-focus hidden>
        <label for="report-violations-only">
          <input id="report-violations-only" type="checkbox" data-report-violations-only
                 aria-controls="component-communication-detail report-secondary-detail flow-graph">
          Violations only
        </label>
        <span>Hide secondary detail; verdicts, failures, unknowns and evidence stay
          available.</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Kind</th><th>Rule</th><th>Finding</th><th>Subjects</th>
          <th>Evidence / baseline</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      <script>{script}</script>
    </section>"""


def _violation_row(
    item: Record,
    observation: Observation,
    *,
    known: bool = False,
) -> str:
    evidence = {entry.id: entry for entry in observation.evidence}
    location = ""
    if item.evidence_ids:
        source = evidence.get(item.evidence_ids[0])
        if source is not None:
            location = f"{source.file}:{source.line}" if source.line else source.file
    owners = component_owners(observation)
    components = sorted(
        {owner for subject in item.subjects if (owner := owner_of(subject, owners)) is not None}
    )
    baseline = ' data-baseline="known"' if known else ""
    known_badge = '<span class="known-badge">KNOWN</span>' if known else ""
    return (
        f'<tr class="violation-row" data-filter-row data-kind="{_text(item.kind)}" '
        f'data-status="FAIL"{baseline} '
        f'data-component="{_text(" ".join(components))}" '
        f'data-search="{_text(" ".join((item.id, item.title, *item.rule_ids, *item.subjects)))}">'
        f'<td><code>{_text(item.id)}</code> <span class="violation-status">FAIL</span> '
        f"{known_badge}</td>"
        f"<td>{_text(item.kind)}</td>"
        f"<td><code>{_text(', '.join(item.rule_ids))}</code></td>"
        f"<td>{_text(item.title)}</td>"
        f"<td><code>{_text(' · '.join(item.subjects))}</code></td>"
        f"<td><code>{_text(location)}</code></td></tr>"
    )


def _violation_group(
    rule_ids: tuple[str, ...],
    items: list[Record],
    observation: Observation,
    comparisons: tuple[BaselineViolationComparison, ...],
) -> str:
    subjects = {tuple(sorted(item.subjects)) for item in items}
    matches = tuple(
        item
        for item in comparisons
        if item.rules == rule_ids and item.subjects in subjects and item.current_count
    )
    known_count = sum(item.shared_count for item in matches)
    new_count = sum(item.new_count for item in matches)
    baseline = f'<span class="known-badge">KNOWN · {known_count}</span>' if known_count else ""
    if new_count:
        baseline += f' <span class="new-badge">NEW · {new_count}</span>'
        if known_count:
            baseline += ' <span class="muted">physical occurrence identity unknown</span>'
    heading = (
        f'<tr class="rule-group" data-group-header><th colspan="6">Rules: '
        f"{_text(', '.join(rule_ids))} · {len(items)} findings {baseline}</th></tr>"
    )
    rows = []
    for item in items:
        fingerprint = tuple(sorted(item.subjects))
        known = any(
            entry.subjects == fingerprint
            and entry.shared_count == entry.current_count
            and entry.new_count == 0
            for entry in matches
        )
        rows.append(_violation_row(item, observation, known=known))
    return heading + "".join(rows)


def _rule_assessments(items: tuple[RuleAssessment, ...] | None) -> str:
    if items is None:
        return ""
    rows = "".join(_rule_assessment_row(item) for item in items)
    return f"""
    <section class="report-section" aria-labelledby="rule-assessments-heading">
      <h2 id="rule-assessments-heading">Declared rules · {len(items)}</h2>
      <p>PASS requires evidence that this rule was checked. Permissions define allowed paths;
      they are not checks. FAIL may also include undecided evidence.</p>
      <div class="table-wrap"><table><thead><tr><th>Rule</th><th>Kind</th><th>Status</th>
      <th>Violations / undecided</th><th>Details</th></tr></thead>
      <tbody>{rows}</tbody></table></div>
    </section>"""


def _rule_assessment_row(item: RuleAssessment) -> str:
    state = "info" if item.status == "DECLARATION" else badge(item.status).state
    provenance = ", ".join(item.provenance) or "—"
    components = ", ".join(item.components) or "—"
    details = " ".join(
        (item.decided_by, item.rationale, provenance, item.scope, components, item.reason)
    )
    return (
        f'<tr data-filter-row data-kind="{_text(item.kind)}" data-status="{_text(item.status)}" '
        f'data-undecided="{item.undecided}" '
        f'data-component="{_text(" ".join(item.components))}" '
        f'data-search="{_text(item.id + " " + item.kind + " " + details)}">'
        f"<td><code>{_text(item.id)}</code></td><td>{_text(item.kind)}</td>"
        f'<td><strong data-status="{state}">{_text(item.status)}</strong></td>'
        '<td class="numeric">'
        f"{item.count} violations · {item.undecided} undecided</td>"
        f"<td><details><summary>Scope, decision and evidence</summary>"
        f"<dl><dt>Decider</dt><dd>{_text(item.decided_by)}</dd>"
        f"<dt>Rationale</dt><dd>{_text(item.rationale or '—')}</dd>"
        f"<dt>Provenance</dt><dd><code>{_text(provenance)}</code></dd>"
        f"<dt>Scope</dt><dd>{_text(item.scope)}</dd>"
        f"<dt>Components</dt><dd>{_text(components)}</dd>"
        f"<dt>Assessment</dt><dd>{_text(item.reason)}</dd></dl></details></td></tr>"
    )


def _calls(rows: tuple[CallRow, ...]) -> str:
    """AD-100: `--only calls` as a table, the same rows `--json` lists as `filtered_calls`."""
    cells = "".join(
        "<tr>"
        f"<td>{_text(row.status)}</td>"
        f"<td><code>{_text(row.expression)}()</code></td>"
        f"<td><code>{_text(row.caller)}</code></td>"
        f"<td>{_text(row.component or 'none')}</td>"
        f"<td>{_text(row.reason)}</td>"
        f"<td><code>{_text(row.path)}:{row.line}</code></td>"
        "</tr>"
        for row in rows
    )
    body = (
        '<div class="table-wrap"><table><thead><tr><th>Status</th><th>Call</th><th>Caller</th>'
        "<th>Component</th><th>Reason</th><th>Location</th></tr></thead>"
        f"<tbody>{cells}</tbody></table></div>"
        if rows
        else "<p>None.</p>"
    )
    return (
        '<section class="report-section"><h2>Unresolved and partially resolved calls</h2>'
        f"{body}</section>"
    )


def _interface_name_line(item: InterfaceName) -> str:
    line = f"<code>{_text(item.name)}</code> {_text(item.kind)}"
    if item.returns:
        params = ", ".join(_text(parameter) for parameter in item.parameters)
        line += f" ({params}) → {_text(item.returns)}"
    return line


def _interface_edge_row(edge: InterfaceEdge) -> str:
    names = "".join(f"<li>{_interface_name_line(item)}</li>" for item in edge.names)
    return (
        '<details class="connection-row">'
        f"<summary><code>{_text(edge.source)} → {_text(edge.target)}</code>"
        f"<span>{len(edge.names)} imported names</span></summary>"
        f"<ul>{names}</ul></details>"
    )


def _interfaces_section(observation: Observation) -> str:
    edges = interface_edges(observation)
    if not edges:
        body = "<p>No cross-component imports were observed.</p>"
    else:
        rows = "".join(_interface_edge_row(edge) for edge in edges)
        body = (
            f'<details class="report-evidence"><summary>All {len(edges)} component pairs · '
            f"{sum(len(edge.names) for edge in edges)} imported names</summary>"
            f'<div class="connection-list">{rows}</div></details>'
        )
    return (
        '<section class="report-section"><h2>Cross-component imports</h2>'
        "<p>Observed imports, not runtime calls or proof of a declared public interface.</p>"
        f"{body}</section>"
    )


def _interface_profile_section(observation: Observation) -> str:
    """Render AD-88 measurements; `validate`, not the report, judges AD-99 budgets."""
    profile = interface_profile(observation)
    if not profile.facades:
        return ""
    facade_rows = "".join(
        "<tr>"
        f"<td><code>{_text(item.component)}</code></td>"
        f"<td><code>{_text(item.module)}</code></td>"
        f'<td class="numeric">{item.exported_name_count}</td>'
        f'<td class="numeric">{item.reexport_count}</td>'
        f"<td>{_text(', '.join(item.defined_names) or '—')}</td>"
        f"<td>{_text(', '.join(item.unused_reexports) or '—')}</td>"
        "</tr>"
        for item in profile.facades
    )
    usage_rows = "".join(
        "<tr>"
        f"<td><code>{_text(item.component)}</code></td>"
        f"<td><code>{_text(item.module + ':' + item.name)}</code></td>"
        f'<td class="numeric">{item.consumer_count}</td>'
        f"<td>{_text(', '.join(item.consumers) or '—')}</td>"
        "</tr>"
        for item in profile.exports
    )
    coupling_rows = "".join(
        "<tr>"
        f"<td><code>{_text(item.source)} → {_text(item.target)}</code></td>"
        f'<td class="numeric">{item.width}</td>'
        f"<td>{_text(', '.join(item.names) or '—')}"
        f"{_text('; not counted: ' + ', '.join(item.uncounted)) if item.uncounted else ''}</td>"
        "</tr>"
        for item in profile.coupling
    )
    return f"""
    <section class="report-section">
      <h2>Public API measurements</h2>
      <p>Observed from declared facades and imports: exported-name count, re-exports, names
      defined in the facade, unused re-exports, consumers per exported name and coupling width.
      They do not claim a barrel is complete (AD-88); <code>validate</code> holds declared
      facade and coupling budgets to them (AD-99).</p>
      <details class="report-evidence"><summary>Facades · {len(profile.facades)}</summary>
      <div class="table-wrap"><table><thead><tr><th>Component</th><th>Module</th>
      <th class="numeric">Exports</th><th class="numeric">Re-exports</th><th>Defined</th>
      <th>Unused re-exports</th></tr></thead><tbody>{facade_rows}</tbody></table></div></details>
      <details class="report-evidence"><summary>Export consumers · {len(profile.exports)}</summary>
      <div class="table-wrap"><table><thead><tr><th>Component</th><th>Export</th>
      <th class="numeric">Consumers</th><th>Components</th></tr></thead>
      <tbody>{usage_rows}</tbody></table></div></details>
      <details class="report-evidence">
      <summary>Coupling width · {len(profile.coupling)} pairs</summary>
      <div class="table-wrap"><table><thead><tr><th>Component pair</th>
      <th class="numeric">Distinct names</th><th>Names</th></tr></thead>
      <tbody>{coupling_rows}</tbody></table></div></details>
    </section>
    """


def _within(qualified: str, module: str) -> str:
    """Drop the module prefix a payload key already carries."""
    return qualified[len(module) + 1 :] if qualified.startswith(f"{module}.") else qualified


def _inner_edge_payload(
    edges: tuple[FlowInnerEdge, ...], sites: dict[tuple[str, ...], set[str]]
) -> list[dict[str, object]]:
    return [
        {
            "source": edge.source,
            "target": edge.target,
            "import_sites": edge.import_sites,
            "rule_ids": list(edge.rule_ids),
            "state": edge.state,
            "sites": sorted(sites.get(("module", edge.source, edge.target), ()))[:3],
        }
        for edge in edges
    ]


def _inside_payload(
    inside: FlowInside | None,
    sites: dict[tuple[str, ...], set[str]],
    parent: str,
) -> dict[str, object] | None:
    """Serialise a declared inside the way `level()` consumes it, or None when none exists."""
    if inside is None:
        return None
    return {
        "components": [
            {
                "label": card.label,
                "modules": list(card.modules),
                "public": list(card.public) if card.public is not None else None,
                "requires": _flow_requirement_entries(card.requires),
                "inner_edges": _inner_edge_payload(card.inner_edges, sites),
                "inside": _inside_payload(card.inside, sites, f"{parent}:{card.label}"),
            }
            for card in inside.components
        ],
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "import_sites": edge.import_sites,
                "rule_ids": list(edge.rule_ids),
                "state": edge.state,
                "sites": sorted(sites.get(("inside", parent, edge.source, edge.target), ()))[:3],
            }
            for edge in inside.edges
        ],
        "unassigned": list(inside.unassigned),
    }


def _flow_sites(observation: Observation) -> dict[tuple[str, ...], set[str]]:
    evidence = {item.id: f"{item.file}:{item.line}" for item in observation.evidence}
    owners = component_owners(observation)
    inside_owners = {
        level.parent: {module: card.label for card in level.components for module in card.modules}
        for level in inside_levels(observation)
    }
    sites: dict[tuple[str, ...], set[str]] = {}
    for item in observation.records("imports") or ():
        source = item.data.get("source_module")
        target = item.data.get("target_module")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        locations = {evidence[key] for key in item.evidence_ids if key in evidence}
        module_pair = ("module", source, target)
        sites[module_pair] = sites.get(module_pair, set()) | locations
        source_owner = owner_of(source, owners)
        target_owner = owner_of(target, owners)
        if source_owner and target_owner:
            pair = ("component", source_owner, target_owner)
            sites[pair] = sites.get(pair, set()) | locations
        for parent, level in inside_owners.items():
            if source in level and target in level:
                inside_pair = ("inside", parent, level[source], level[target])
                sites[inside_pair] = sites.get(inside_pair, set()) | locations
    return sites


def _flow_requires(record: Record | None) -> list[dict[str, object]]:
    if record is None:
        return []
    entries = record.data.get("requires")
    if not isinstance(entries, tuple):
        return []
    return _flow_requirement_entries(
        tuple(entry for entry in entries if isinstance(entry, RecordData))
    )


def _flow_requirement_entries(entries: tuple[RecordData, ...]) -> list[dict[str, object]]:
    return [
        {
            "component": entry.get("component"),
            "through": entry.get("through") or (),
            "rationale": entry.get("rationale"),
            "decided_by": entry.get("decided_by"),
        }
        for entry in entries
    ]


def _flow_modules_payload(flow: FlowData) -> dict[str, object]:
    # Symbol names are relative to the module that keys them; repeating the prefix on
    # every card and edge would multiply a large report payload.
    return {
        name: {
            "symbols": [
                {
                    "name": _within(symbol.name, name),
                    "kind": symbol.kind,
                    "visibility": symbol.visibility,
                    "members": list(symbol.members),
                }
                for symbol in module.symbols
            ],
            "edges": [
                {"source": _within(edge.source, name), "target": _within(edge.target, name)}
                for edge in module.edges
            ],
            "exports": list(module.exports),
            "imports": list(module.imports),
        }
        for name, module in sorted(flow.modules.items())
    }


def _library_imports(observation: Observation, dependency: str) -> dict[str, list[Record]]:
    owners = component_owners(observation)
    matching = [
        (owner_of(source, owners), item)
        for item in observation.records("imports") or ()
        if isinstance(source := item.data.get("source_module"), str)
        and isinstance(target := item.data.get("target_module"), str)
        and in_scope(target, dependency)
    ]
    return {
        owner: [item for source, item in matching if source == owner]
        for owner in sorted({source for source, _ in matching if source is not None})
    }


def _library_scope_rules(scopes: list[Record], evidence: dict[str, str]) -> list[dict[str, object]]:
    rules: list[dict[str, object]] = []
    for scope in scopes:
        allowed_sources = scope.data.get("allowed_sources")
        exact_sources = scope.data.get("exact_sources")
        rules.append(
            {
                "rule_id": scope.id,
                "rationale": scope.data.get("rationale"),
                "decided_by": scope.data.get("decided_by"),
                "provenance": list(scope.provenance),
                "allowed_sources": [value for value in allowed_sources if isinstance(value, str)]
                if isinstance(allowed_sources, tuple)
                else [],
                "exact_sources": [value for value in exact_sources if isinstance(value, str)]
                if isinstance(exact_sources, tuple)
                else [],
                "evidence": sorted(evidence[key] for key in scope.evidence_ids if key in evidence),
            }
        )
    return sorted(rules, key=lambda rule: str(rule["rule_id"]))


def _library_edge(
    source: str,
    items: list[Record],
    label: str,
    scope_rules: list[dict[str, object]],
    violated_imports: set[tuple[str, str]],
    evidence: dict[str, str],
) -> dict[str, object]:
    broken_rules = [
        rule
        for rule in scope_rules
        if any((item.id, rule["rule_id"]) in violated_imports for item in items)
    ]
    return {
        "source": source,
        "target": label,
        "import_sites": len(items),
        "rule_ids": [rule["rule_id"] for rule in broken_rules],
        "state": "violation" if broken_rules else "conforms",
        "sites": sorted(
            {evidence[key] for item in items for key in item.evidence_ids if key in evidence}
        )[:3],
        "requirement": {},
        "scope": {"rules": scope_rules},
        "library": True,
        "names": [],
    }


def _flow_libraries(
    observation: Observation,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    scopes_by_dependency: dict[str, list[Record]] = {}
    for item in observation.records("declarations") or ():
        dependency = item.data.get("dependency")
        if (
            item.kind == "external_dependency_scope"
            and item.data.get("parent_id") is None
            and isinstance(dependency, str)
        ):
            scopes_by_dependency[dependency] = [
                *scopes_by_dependency.get(dependency, []),
                item,
            ]
    evidence = {item.id: f"{item.file}:{item.line}" for item in observation.evidence}
    violated_imports = {
        (fact_id, rule_id)
        for item in observation.records("violations") or ()
        for fact_id in item.fact_ids
        for rule_id in item.rule_ids
    }
    libraries: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    for dependency, scopes in sorted(scopes_by_dependency.items()):
        grouped = _library_imports(observation, dependency)
        if not grouped:
            continue
        label = f"library:{dependency}"
        scope_rules = _library_scope_rules(scopes, evidence)
        library = {
            "label": label,
            "display": dependency,
            "library": True,
            "modules": [],
            "public": None,
            "import_sites": sum(len(grouped[source]) for source in grouped),
            "rules": scope_rules,
        }
        if len(scope_rules) == 1:
            rule = scope_rules[0]
            for key in (
                "rationale",
                "decided_by",
                "provenance",
                "allowed_sources",
                "exact_sources",
                "evidence",
            ):
                library[key] = rule[key]
            library["rule_id"] = rule["rule_id"]
        libraries.append(library)
        for source, items in sorted(grouped.items()):
            edges.append(
                _library_edge(source, items, label, scope_rules, violated_imports, evidence)
            )
    return sorted(libraries, key=lambda item: str(item["label"])), edges


def _flow_component_payload(
    component: FlowComponent,
    sites: dict[tuple[str, ...], set[str]],
    requires: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    return {
        "label": component.label,
        "modules": list(component.modules),
        "public": list(component.public) if component.public is not None else None,
        "requires": requires.get(component.label, []),
        "inner_edges": _inner_edge_payload(component.inner_edges, sites),
        "inside": _inside_payload(component.inside, sites, component.label),
    }


def _flow_edge_payload(
    edge: FlowEdge,
    sites: dict[tuple[str, ...], set[str]],
    requires: dict[str, list[dict[str, object]]],
    names_by_pair: dict[tuple[str, str], tuple[InterfaceName, ...]],
) -> dict[str, object]:
    return {
        "source": edge.source,
        "target": edge.target,
        "import_sites": edge.import_sites,
        "rule_ids": list(edge.rule_ids),
        "state": edge.state,
        "sites": sorted(sites.get(("component", edge.source, edge.target), ()))[:3],
        "requirement": next(
            (entry for entry in requires.get(edge.source, []) if entry["component"] == edge.target),
            {},
        ),
        "names": [
            {
                "name": name.name,
                "kind": name.kind,
                "params": list(name.parameters),
                "returns": name.returns,
            }
            for name in names_by_pair.get((edge.source, edge.target), ())
        ],
    }


def _unique_flow_label(label: str, occupied: set[str]) -> tuple[str, set[str]]:
    candidate = label
    suffix = 2
    while candidate in occupied:
        candidate = f"{label} ({suffix})"
        suffix += 1
    return candidate, occupied | {candidate}


def _collision_free_library_labels(
    components: tuple[FlowComponent, ...],
    libraries: list[dict[str, object]],
    edges: list[dict[str, object]],
    has_unassigned: bool,
) -> str | None:
    occupied = {component.label for component in components}
    for library in libraries:
        old = str(library["label"])
        new, occupied = _unique_flow_label(old, occupied)
        if new != old:
            library["label"] = new
            for edge in edges:
                if edge["target"] == old:
                    edge["target"] = new
    if has_unassigned:
        label, _ = _unique_flow_label("Unassigned modules", occupied)
        return label
    return None


def _add_actual_module(tree: dict[str, dict[str, object]], name: str, file: str) -> None:
    parts = name.split(".")
    siblings = tree
    path: list[str] = []
    for part in parts:
        path.append(part)
        qualified = ".".join(path)
        if qualified not in siblings:
            siblings[qualified] = {
                "id": qualified,
                "label": part,
                "children": {},
                "file": None,
            }
        node = siblings[qualified]
        children = node["children"]
        if not isinstance(children, dict):
            raise TypeError("actual module tree children must be a mapping")
        siblings = children
    node["file"] = file


def _finish_actual_node(node: dict[str, object]) -> dict[str, object]:
    children = node["children"]
    if not isinstance(children, dict):
        raise TypeError("actual module tree children must be a mapping")
    file = node["file"]
    return {
        "id": node["id"],
        "label": node["label"],
        "kind": "module" if isinstance(file, str) else "group",
        "details": [{"label": "File", "value": file}] if isinstance(file, str) else [],
        "children": [_finish_actual_node(children[key]) for key in children],
    }


def _scoped_layout_records(
    layouts_by_parent: dict[str | None, list[Record]],
    nested_layout_ids: set[str],
    parent: str | None,
) -> list[Record]:
    return [
        record for record in layouts_by_parent.get(parent, ()) if record.id not in nested_layout_ids
    ]


def _target_layout_node(
    record: Record, layouts_by_root: dict[str, list[Record]]
) -> dict[str, object]:
    root = record.data.get("root")
    allowed = record.data.get("allowed_children")
    root_name = root if isinstance(root, str) else record.title
    children = (
        [name for name in allowed if isinstance(name, str)] if isinstance(allowed, tuple) else []
    )
    return {
        "id": f"layout:{record.id}",
        "label": root_name,
        "kind": "root_layout",
        "details": [{"label": "Allowed children", "value": ", ".join(children)}],
        "children": [
            {
                "id": f"physical:{name}",
                "label": name,
                "kind": "physical_child",
                "details": [{"label": "Allowed by", "value": root_name}],
                "children": [
                    _target_layout_node(child_layout, layouts_by_root)
                    for child_layout in layouts_by_root.get(name, ())
                ],
            }
            for name in children
        ],
    }


def _target_component_details(record: Record, packages: list[str]) -> list[dict[str, object]]:
    details: list[dict[str, object]] = [{"label": "Packages", "value": ", ".join(packages)}]
    responsibilities = record.data.get("responsibilities")
    if isinstance(responsibilities, tuple):
        details.extend(
            {"label": "Responsibility", "value": sentence}
            for sentence in responsibilities
            if isinstance(sentence, str)
        )
    return details


def _target_component_node(
    record: Record,
    component_keys: dict[str, str],
    children_by_parent: dict[str, list[Record]],
    layouts_by_parent: dict[str | None, list[Record]],
    nested_layout_ids: set[str],
    layouts_by_root: dict[str, list[Record]],
) -> dict[str, object]:
    packages = list(record.subjects)
    details = _target_component_details(record, packages)
    key = component_keys[record.id]
    nested = [
        _target_component_node(
            child,
            component_keys,
            children_by_parent,
            layouts_by_parent,
            nested_layout_ids,
            layouts_by_root,
        )
        for child in children_by_parent.get(key, ())
    ]
    nested.extend(
        _target_layout_node(layout, layouts_by_root)
        for layout in _scoped_layout_records(layouts_by_parent, nested_layout_ids, key)
    )
    nested.extend(
        {
            "id": f"package:{record.id}:{package}",
            "label": package,
            "kind": "package_scope",
            "details": [
                {"label": "Owner", "value": record.title},
                {"label": "Package scope", "value": package},
            ],
            "children": [],
        }
        for package in packages
    )
    nested.extend(
        {
            "id": f"requires:{record.id}:{entry['component']}",
            "label": f"requires {entry['component']}",
            "kind": "requires",
            "details": [
                {"label": "Rationale", "value": entry.get("rationale") or "Declared dependency"},
                *(
                    [{"label": "Decided by", "value": entry["decided_by"]}]
                    if isinstance(entry.get("decided_by"), str)
                    else []
                ),
            ],
            "children": [],
        }
        for entry in _flow_requires(record)
        if isinstance(entry.get("component"), str)
    )
    return {
        "id": record.id,
        "label": record.title,
        "kind": "component",
        "details": details,
        "children": nested,
    }


def _explorer_group(
    identifier: str, label: str, kind: str, children: list[dict[str, object]]
) -> dict[str, object]:
    return {"id": identifier, "label": label, "kind": kind, "details": [], "children": children}


def _target_roots(
    declarations: tuple[Record, ...],
) -> tuple[list[dict[str, object]], dict[str, Record], list[Record]]:
    components = {
        record.id: record
        for record in declarations
        if record.kind in {"component_responsibility", "inside_component_responsibility"}
    }
    component_keys = {
        record.id: (
            f"{record.data.get('parent_id')}:{record.title}"
            if isinstance(record.data.get("parent_id"), str)
            else record.title
        )
        for record in components.values()
    }
    children_by_parent: dict[str, list[Record]] = {}
    layouts_by_parent: dict[str | None, list[Record]] = {}
    for record in components.values():
        parent = record.data.get("parent_id")
        if isinstance(parent, str):
            children_by_parent[parent] = [*children_by_parent.get(parent, ()), record]
    layout_records = [record for record in declarations if record.kind == "root_layout"]
    for record in layout_records:
        parent = record.data.get("parent_id")
        parent_key = parent if isinstance(parent, str) else None
        layouts_by_parent[parent_key] = [*layouts_by_parent.get(parent_key, ()), record]
    layouts_by_root = {
        root: [record for record in layout_records if record.data.get("root") == root]
        for root in {record.data.get("root") for record in layout_records}
        if isinstance(root, str)
    }
    nested_layout_ids = {
        child.id
        for parent in layout_records
        if isinstance(allowed := parent.data.get("allowed_children"), tuple)
        for root in allowed
        if isinstance(root, str)
        for child in layouts_by_root.get(root, ())
        if child.id != parent.id
    }

    target_roots = [
        _target_component_node(
            record,
            component_keys,
            children_by_parent,
            layouts_by_parent,
            nested_layout_ids,
            layouts_by_root,
        )
        for record in components.values()
        if record.kind == "component_responsibility" and record.data.get("parent_id") is None
    ]
    target_roots.extend(
        _target_layout_node(record, layouts_by_root)
        for record in _scoped_layout_records(layouts_by_parent, nested_layout_ids, None)
    )

    return target_roots, components, layout_records


def _finish_module_target_nodes(
    node: dict[str, object], prefix: tuple[str, ...] = ()
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    child_folders = node["folders"]
    if not isinstance(child_folders, dict):
        raise TypeError("module target folders must be a mapping")
    for label, child in sorted(child_folders.items()):
        if not isinstance(child, dict):
            raise TypeError("module target node must be a mapping")
        children = _finish_module_target_nodes(child, (*prefix, label))
        result.append(
            {
                "id": f"module-folder:{'/'.join((*prefix, label))}",
                "label": label,
                "kind": "folder",
                "details": [],
                "children": children,
            }
        )
    targets = node["targets"]
    if isinstance(targets, list):
        result.extend(targets)
    return result


def _target_module_nodes(records: list[Record]) -> list[dict[str, object]]:
    root: dict[str, object] = {"folders": {}, "targets": []}
    for record in records:
        path = record.data.get("path")
        if not isinstance(path, str):
            continue
        node = root
        parts = re.split("/", path)
        for part in parts[:-1]:
            child_folders = node["folders"]
            if not isinstance(child_folders, dict):
                raise TypeError("module target folders must be a mapping")
            child = child_folders.get(part)
            if not isinstance(child, dict):
                child = {"folders": {}, "targets": []}
                child_folders[part] = child
            node = child
        targets = node["targets"]
        if not isinstance(targets, list):
            raise TypeError("module target leaves must be a list")
        node["targets"] = [
            *targets,
            {
                "id": record.id,
                "label": parts[-1],
                "kind": "module_target",
                "details": [
                    {"label": "File", "value": path},
                    {"label": "Responsibility", "value": record.data.get("responsibility")},
                ],
                "children": [],
            },
        ]
    return _finish_module_target_nodes(root)


def _absent_targets(
    observation: Observation,
    modules: dict[str, str],
    components: dict[str, Record],
    layouts: list[Record],
    module_targets: list[Record],
) -> list[dict[str, object]]:
    observed_paths = set(modules) | {
        name
        for record in observation.records("packages") or ()
        if (name := record.data.get("qualified_name")) and isinstance(name, str)
    }
    absent_targets: list[dict[str, object]] = []
    observed_files = set(modules.values())
    for record in module_targets:
        path = record.data.get("path")
        if not isinstance(path, str) or path in observed_files:
            continue
        absent_targets.append(
            {
                "id": f"absent:{record.id}",
                "label": path,
                "kind": "module_target",
                "details": [
                    {"label": "Responsibility", "value": record.data.get("responsibility")}
                ],
                "children": [],
            }
        )
    for record in components.values():
        missing_packages = [
            package
            for package in record.subjects
            if not any(in_scope(name, package) for name in observed_paths)
        ]
        for package in missing_packages:
            absent_targets.append(
                {
                    "id": f"absent:{record.id}:{package}",
                    "label": package,
                    "kind": "package_scope",
                    "details": [{"label": "Component", "value": record.title}],
                    "children": [],
                }
            )
        if missing_packages and len(missing_packages) == len(record.subjects):
            absent_targets.append(
                {
                    "id": f"absent:{record.id}",
                    "label": record.title,
                    "kind": "component",
                    "details": [{"label": "Packages", "value": ", ".join(record.subjects)}],
                    "children": [],
                }
            )
    for record in layouts:
        allowed = record.data.get("allowed_children")
        if not isinstance(allowed, tuple):
            continue
        for child in allowed:
            if not isinstance(child, str) or any(in_scope(name, child) for name in observed_paths):
                continue
            absent_targets.append(
                {
                    "id": f"absent:{record.id}:{child}",
                    "label": child,
                    "kind": "physical_child",
                    "details": [{"label": "Expected below", "value": str(record.data.get("root"))}],
                    "children": [],
                }
            )

    return absent_targets


def _unmapped_targets(
    observation: Observation, flow: FlowData, modules: dict[str, str], components: dict[str, Record]
) -> set[str]:
    owned_package_paths = {package for record in components.values() for package in record.subjects}
    initializer_targets = {
        name
        for name, file in modules.items()
        if name in owned_package_paths and file[-11:] == "__init__.py"
    }
    unmapped = set(flow.unassigned_modules) - initializer_targets
    for level in inside_levels(observation):
        unmapped |= set(level.unassigned) - initializer_targets
    return unmapped


def _target_projection(
    observation: Observation,
    flow: FlowData,
    modules: dict[str, str],
    declarations: tuple[Record, ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]], set[str]]:
    target_roots, components, layouts = _target_roots(declarations)
    module_targets = [record for record in declarations if record.kind == "module_target"]
    if module_targets:
        target_roots = [
            *target_roots,
            _explorer_group(
                "module-targets",
                "Declared modules",
                "category",
                _target_module_nodes(module_targets),
            ),
        ]
    return (
        target_roots,
        _absent_targets(observation, modules, components, layouts, module_targets),
        _unmapped_targets(observation, flow, modules, components),
    )


def _graph_node(node: dict[str, object]) -> dict[str, object]:
    return {key: node[key] for key in ("id", "label", "kind", "details")}


def _target_children(node: dict[str, object]) -> list[dict[str, object]]:
    children = node["children"]
    return children if isinstance(children, list) else []


def _target_tree(nodes: list[dict[str, object]]) -> list[dict[str, object]]:
    return [node for item in nodes for node in [item, *_target_tree(_target_children(item))]]


def _target_nested_graph(node: dict[str, object]) -> dict[str, object] | None:
    children = _target_children(node)
    if not children:
        return None
    nodes = [_graph_node(node)]
    edges = []
    for child in children:
        if child["kind"] == "requires":
            continue
        nodes.append(_graph_node(child))
        kind = (
            "owns_package"
            if child["kind"] == "package_scope"
            else "allowed_child"
            if node["kind"] == "root_layout" and child["kind"] == "physical_child"
            else "contains"
        )
        edges.append(
            {
                "source": node["id"],
                "target": child["id"],
                "kind": kind,
                "label": child["label"],
                "details": child["details"],
                "declaration": child["id"],
            }
        )
    for child in children:
        if child["kind"] != "component":
            continue
        edges.extend(_nested_requires_edges(child, children, nodes))
    edges.extend(_nested_requires_edges(node, children, nodes))
    return {"owner": node["id"], "nodes": nodes, "edges": edges}


def _nested_requires_edges(
    owner: dict[str, object], siblings: list[dict[str, object]], nodes: list[dict[str, object]]
) -> list[dict[str, object]]:
    edges = []
    for requirement in _target_children(owner):
        if requirement["kind"] != "requires":
            continue
        label = requirement["label"]
        if not isinstance(label, str):
            continue
        target_name = label[9:]
        target = next((item for item in siblings if item["label"] == target_name), requirement)
        if not any(item["id"] == target["id"] for item in nodes):
            nodes.append(_graph_node(target))
        edges.append(
            {
                "source": owner["id"],
                "target": target["id"],
                "kind": "requires",
                "label": label,
                "details": requirement["details"],
                "declaration": requirement["id"],
            }
        )
    return edges


def _root_requires_edges(
    components: list[dict[str, object]], nodes: list[dict[str, object]]
) -> list[dict[str, object]]:
    edges = []
    for component in components:
        for requirement in _target_children(component):
            if requirement["kind"] != "requires":
                continue
            requirement_label = requirement["label"]
            if not isinstance(requirement_label, str):
                continue
            target_label = requirement_label[9:]
            target = next((node for node in components if node["label"] == target_label), None)
            if target is None:
                target = requirement
                nodes.append(_graph_node(target))
            edges.append(
                {
                    "source": component["id"],
                    "target": target["id"],
                    "kind": "requires",
                    "label": requirement["label"],
                    "details": requirement["details"],
                    "declaration": requirement["id"],
                }
            )
    return edges


def _root_target_graph(target_roots: list[dict[str, object]]) -> dict[str, object]:
    components = [node for node in target_roots if node["kind"] == "component"]
    root_nodes = [_graph_node(node) for node in target_roots]
    root_edges: list[dict[str, object]] = []
    root_edges.extend(_root_requires_edges(components, root_nodes))
    return {"owner": None, "nodes": root_nodes, "edges": root_edges}


def _target_diagrams(target_roots: list[dict[str, object]]) -> dict[str, object]:
    nested = {
        str(node["id"]): graph
        for node in _target_tree(target_roots)
        if (graph := _target_nested_graph(node)) is not None
    }
    return {"root": _root_target_graph(target_roots), "nested": nested}


def _explorer_violation_rows(observation: Observation) -> list[dict[str, object]]:
    violation_rows: list[dict[str, object]] = [
        {
            "id": record.id,
            "label": record.title,
            "kind": "violation",
            "details": [
                {"label": "Rule", "value": ", ".join(record.rule_ids)},
                *(
                    [{"label": "Violating edge", "value": f"{source} → {target}"}]
                    if isinstance(
                        source := record.data.get("source_component")
                        or record.data.get("source_module"),
                        str,
                    )
                    and isinstance(
                        target := record.data.get("target_component")
                        or record.data.get("target_module"),
                        str,
                    )
                    else []
                ),
                {"label": "Subjects", "value": ", ".join(record.subjects)},
            ],
            "children": [],
        }
        for record in observation.records("violations") or ()
    ]
    return violation_rows


def _explorer_unknown_rows(observation: Observation) -> list[dict[str, object]]:
    return [
        {
            "id": record.id,
            "label": record.title,
            "kind": "unknown",
            "details": [
                {"label": "Kind", "value": record.kind},
                {"label": "Rules", "value": ", ".join(record.rule_ids)},
                {"label": "Subjects", "value": ", ".join(record.subjects)},
            ],
            "children": [],
        }
        for record in observation.records("unknowns") or ()
    ]


def _explorer_diff(
    observation: Observation,
    modules: dict[str, str],
    absent_targets: list[dict[str, object]],
    unmapped: set[str],
    observed_only_targets: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        _explorer_group(
            "diff:violations",
            "Violations",
            "category",
            sorted(_explorer_violation_rows(observation), key=lambda item: str(item["label"])),
        ),
        _explorer_group(
            "diff:unknowns",
            "Unknown / unresolved evidence",
            "category",
            sorted(_explorer_unknown_rows(observation), key=lambda item: str(item["label"])),
        ),
        _explorer_group(
            "diff:unmapped",
            "Unmapped observed modules",
            "category",
            [
                {
                    "id": f"unmapped:{name}",
                    "label": name,
                    "kind": "module",
                    "details": [{"label": "File", "value": modules.get(name, "Unknown file")}],
                    "children": [],
                }
                for name in sorted(unmapped)
            ],
        ),
        _explorer_group(
            "diff:observed-only-targets",
            "Observed modules without a declared target",
            "category",
            observed_only_targets,
        ),
        _explorer_group(
            "diff:absent",
            "Absent declared targets",
            "category",
            sorted(absent_targets, key=lambda item: str(item["label"])),
        ),
    ]


def _explorer_payload(observation: Observation, flow: FlowData) -> dict[str, object]:
    modules = {
        name: file
        for record in observation.records("modules") or ()
        if (name := record.data.get("qualified_name"))
        and isinstance(name, str)
        and (file := record.data.get("file"))
        and isinstance(file, str)
    }
    actual_tree: dict[str, dict[str, object]] = {}
    for name, file in sorted(modules.items()):
        _add_actual_module(actual_tree, name, file)
    declarations = observation.records("declarations") or ()
    target, absent, unmapped = _target_projection(observation, flow, modules, declarations)
    module_targets = [record for record in declarations if record.kind == "module_target"]
    declared_files = {
        path for record in module_targets if isinstance((path := record.data.get("path")), str)
    }
    observed_only_targets: list[dict[str, object]] = [
        {
            "id": f"observed-only-target:{name}",
            "label": path,
            "kind": "observed_only_module_target",
            "details": [
                {"label": "File", "value": path},
                {"label": "Module", "value": name},
            ],
            "children": [],
        }
        for name, path in sorted(modules.items())
        if module_targets and path not in declared_files
    ]
    return {
        "actual": [_finish_actual_node(actual_tree[key]) for key in actual_tree],
        "target": target,
        "target_diagrams": _target_diagrams(target),
        "diff": _explorer_diff(observation, modules, absent, unmapped, observed_only_targets),
    }


def _flow_payload(observation: Observation, flow: FlowData) -> dict[str, object]:
    names_by_pair = {
        (edge.source, edge.target): edge.names for edge in interface_edges(observation)
    }
    declarations = observation.records("declarations") or ()
    by_component = {
        record.title: record for record in declarations if record.kind == "component_responsibility"
    }
    rules = {
        record.id: {
            "rationale": record.data.get("rationale"),
            "decided_by": record.data.get("decided_by"),
        }
        for record in declarations
        if record.data.get("rationale") is not None
    }
    sites = _flow_sites(observation)
    requires = {label: _flow_requires(record) for label, record in by_component.items()}
    libraries, library_edges = _flow_libraries(observation)
    unassigned_label = _collision_free_library_labels(
        flow.components, libraries, library_edges, bool(flow.unassigned_modules)
    )

    return {
        "rules": rules,
        "libraries": libraries,
        "components": [
            _flow_component_payload(component, sites, requires) for component in flow.components
        ],
        "unassigned": (
            {
                "label": unassigned_label,
                "display": "Unassigned modules",
                "modules": list(flow.unassigned_modules),
                "public": None,
                "requires": [],
                "inner_edges": _inner_edge_payload(flow.unassigned_edges, sites),
                "inside": None,
                "navigation_only": True,
            }
            if flow.unassigned_modules
            else None
        ),
        "edges": [_flow_edge_payload(edge, sites, requires, names_by_pair) for edge in flow.edges]
        + library_edges,
        "modules": _flow_modules_payload(flow),
        "explorers": _explorer_payload(observation, flow),
    }


_FLOW_GUIDE = """
      <details class="flow-how-to-read"><summary>How to read this report</summary>
        <p>Level 2 shows declared components. If modules have no unique declared owner, an
        “Unassigned modules” card provides navigation only; it is not a component or a boundary.
        A circle marks a provided interface; a socket
        marks a declared dependency. A ball-and-socket on an arrow marks an observed use
        narrowed to a specific interface by <code>through</code>. Arrows are observed imports
        from user to provider, not every dependency the contract permits. Teal conforms,
        red breaks a rule, amber needs a decision, and grey shows imports inside a component.
        A <code>«library»</code> box and dashed teal arrow show observed use of a scoped
        external dependency; a forbidden use is red.
        All components and connections appear by default. Focus narrows the diagram to one box
        and its direct connections; all violations at that level remain visible. Select a box
        twice for level 3: physical package folders and modules inside it.
        Folders are not declared architectural boundaries. Open a module for level 4 symbols.
        Scroll the diagram horizontally or vertically; use Zoom Out, 100%, Zoom In, and Fit
        Overview to control its scale. Arrange resets the card layout. Use the breadcrumb to go
        back. Hover or select a connection for its evidence. Level 1,
        interfaces between repositories, is unavailable because this observation contains
        no cross-repository interface contract. Actual lists every observed module. Target
        contains declared components, requirements and root-layout children only. Diff lists
        recorded violations, unmapped modules and declared targets not found in the observation.
        These three views navigate independently and do not infer contract state from imports.
        The import evidence below works without JavaScript.</p>
      </details>
"""


_FLOW_SVG = """
<svg id="flow-graph" class="flow-graph" role="group" aria-label="Component flow diagram">
  <defs>
    <!-- markerUnits defaults to strokeWidth, which made the arrow a multiple of the
         line: a heavy edge grew a 26px head, a light one 8px, so the size read as
         weight instead of direction. userSpaceOnUse keeps every head the same. -->
    <marker id="flow-arrow-conforms" class="flow-arrow conforms" viewBox="0 0 8 8"
            refX="6" refY="4" markerWidth="8" markerHeight="8"
            markerUnits="userSpaceOnUse" orient="auto-start-reverse">
      <path d="M0,0.5 L7,4 L0,7.5 z"></path>
    </marker>
    <marker id="flow-arrow-violation" class="flow-arrow violation" viewBox="0 0 8 8"
            refX="6" refY="4" markerWidth="8" markerHeight="8"
            markerUnits="userSpaceOnUse" orient="auto-start-reverse">
      <path d="M0,0.5 L7,4 L0,7.5 z"></path>
    </marker>
    <marker id="flow-arrow-undecided" class="flow-arrow undecided" viewBox="0 0 8 8"
            refX="6" refY="4" markerWidth="8" markerHeight="8"
            markerUnits="userSpaceOnUse" orient="auto-start-reverse">
      <path d="M0,0.5 L7,4 L0,7.5 z"></path>
    </marker>
    <marker id="flow-arrow-observed" class="flow-arrow observed" viewBox="0 0 8 8"
            refX="6" refY="4" markerWidth="8" markerHeight="8"
            markerUnits="userSpaceOnUse" orient="auto-start-reverse">
      <path d="M0,0.5 L7,4 L0,7.5 z"></path>
    </marker>
  </defs>
  <g class="flow-viewport">
    <g class="flow-edges"></g>
    <g class="flow-chips"></g>
    <g class="flow-nodes"></g>
    <g class="flow-empty"></g>
  </g>
</svg>"""


def _flow_section(observation: Observation) -> str:
    """Render the AD-10 component flow view: an SVG diagram plus its canonical JSON data."""
    flow = build_flow(observation)
    # Canonical, sorted-key JSON keeps report bytes deterministic; `<` is escaped because this
    # value is embedded inside a <script> element, where a literal "</script" would close it.
    payload = json.dumps(_flow_payload(observation, flow), sort_keys=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c")
    script = _asset("flow.js").decode("utf-8")
    return f"""
    <section class="report-section flow-section" aria-labelledby="flow-heading">
      <h2 id="flow-heading">Component flow</h2>
      {_FLOW_GUIDE}
      <div id="flow" class="flow">
        <nav class="flow-views" aria-label="Architecture views" hidden>
          <button type="button" data-flow-view="diagram" aria-pressed="true">Diagram</button>
          <button type="button" data-flow-view="structure" aria-pressed="false">Structure</button>
          <button type="button" data-flow-view="review" aria-pressed="false">Review</button>
          <button type="button" data-flow-view="actual" aria-pressed="false">Actual</button>
          <button type="button" data-flow-view="target" aria-pressed="false">Target</button>
          <button type="button" data-flow-view="diff" aria-pressed="false">Diff</button>
        </nav>
        <div class="flow-toolbar" hidden>
          <label class="flow-diagram-control flow-diagram-filter" for="flow-focus">Focus
            <select id="flow-focus" class="flow-focus"></select>
          </label>
          <button type="button"
                  class="flow-fit flow-reset-filters flow-diagram-control flow-diagram-filter">
            Reset filters</button>
          <output class="flow-filter-status flow-diagram-control flow-diagram-filter"
                  role="status" aria-live="polite">
            No diagram filters active
          </output>
          <label class="flow-violation-focus flow-diagram-control flow-diagram-filter"
                 for="flow-violations-only" hidden>
            <input id="flow-violations-only" class="flow-violations-only" type="checkbox"
                   aria-controls="flow-graph">
            Violating edges only
          </label>
          <label class="flow-diagram-control flow-diagram-filter"
                 for="flow-threshold-input">Minimum import sites</label>
          <input id="flow-threshold-input"
                 class="flow-threshold flow-diagram-control flow-diagram-filter"
                 type="range" min="0" value="0" aria-describedby="flow-threshold-value">
          <output id="flow-threshold-value"
                  class="flow-threshold-value flow-diagram-control flow-diagram-filter">
            ≥ 0 import sites
          </output>
          <button type="button" class="flow-back flow-navigation-control" hidden>
            Back to components</button>
          <nav class="flow-breadcrumb flow-navigation-control"
               aria-label="Diagram breadcrumb"></nav>
          <div class="flow-zoom-controls flow-diagram-control" role="group"
               aria-label="Diagram zoom">
            <button type="button" class="flow-fit flow-zoom-out" aria-label="Zoom out">−</button>
            <button type="button" class="flow-fit flow-zoom-100"
                    aria-label="Set zoom to 100%">100%</button>
            <output class="flow-zoom-value" aria-live="polite">100%</output>
            <button type="button" class="flow-fit flow-zoom-in" aria-label="Zoom in">+</button>
            <button type="button" class="flow-fit flow-fit-overview">Fit overview</button>
          </div>
          <button type="button" class="flow-fit flow-arrange flow-diagram-control"
                  title="Lay the cards out again">Arrange</button>
        </div>
        <div class="flow-layout">
          <div class="flow-canvas" tabindex="0" role="region"
               aria-label="Scrollable component flow diagram">
            {_FLOW_SVG}
          </div>
          <div class="flow-alternative" hidden></div>
          <aside class="flow-inspector" aria-label="Selection details"></aside>
        </div>
        <div class="flow-legend" aria-label="Legend"></div>
      </div>
      <script id="flow-data" type="application/json">{payload}</script>
      <script>{script}</script>
    </section>"""


def _measurements(measurements: Measurements | None) -> str:
    if measurements is None:
        return "<p>No complete measurements are available.</p>"
    rows = "".join(
        f"<tr><td><code>{_text(name)}</code></td>"
        f'<td class="numeric">{"n/a" if value is None else value}</td></tr>'
        for name, value in measurements.scalars.items()
    )
    ratio = (
        "n/a"
        if measurements.resolution == "n/a"
        else f"{measurements.scalars.calls_unresolved}/{measurements.calls_total}"
    )
    total = measurements.calls_total
    rows += (
        f'<tr><td><code>calls_total</code></td><td class="numeric">{total}</td></tr>'
        f'<tr><td><code>unresolved_ratio</code></td><td class="numeric">{ratio}</td></tr>'
    )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Measurement</th>'
        f'<th class="numeric">Value</th></tr></thead><tbody>{rows}</tbody></table></div>'
    )


def _coverage(observation: Observation | None) -> str:
    if observation is None:
        return "<p>No observation is available.</p>"
    coverage = observation.coverage
    resolution = (
        "n/a"
        if coverage.calls_analyzed == 0
        else (
            f"{coverage.calls_resolved}/{coverage.calls_analyzed} "
            f"({coverage.call_resolution_percent:.2f}%)"
        )
    )
    rows = (
        ("Status", coverage.status),
        ("Rules coverage", coverage.rules or "UNKNOWN"),
        ("Files discovered", coverage.files_discovered),
        ("Files read", coverage.files_read),
        ("Files parsed", coverage.files_parsed),
        ("AST coverage", f"{coverage.files_parsed}/{coverage.files_discovered}"),
        ("Calls resolved", resolution),
        ("Calls partially resolved", coverage.calls_partially_resolved),
        ("Calls unresolved", coverage.calls_unresolved),
    )
    body = "".join(
        f'<tr><td>{_text(label)}</td><td class="numeric"><code>{_text(value)}</code></td></tr>'
        for label, value in rows
    )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Coverage dimension</th>'
        f'<th class="numeric">Evidence</th></tr></thead><tbody>{body}</tbody></table></div>'
    )


def _section_inventory(observation: Observation | None) -> str:
    if observation is None:
        return "<p>No ArchitectureIR sections are available.</p>"
    rows = "".join(
        f"<tr><td><code>{_text(section.name)}</code></td>"
        f'<td class="numeric">{len(section.records)}</td></tr>'
        for section in observation.sections
    )
    modules = sorted(
        name
        for item in observation.records("modules") or ()
        if isinstance(name := item.data.get("qualified_name"), str)
    )
    module_tree = (
        f"<details><summary>Observed module tree · {len(modules)} modules</summary>"
        f"{_module_tree_html(modules)}</details>"
        if modules
        else ""
    )
    return (
        '<div class="table-wrap"><table><thead><tr><th>ArchitectureIR section</th>'
        f'<th class="numeric">Records</th></tr></thead><tbody>{rows}</tbody></table></div>'
        f"{module_tree}"
    )


ModuleTree: TypeAlias = dict[str, "ModuleTree"]


def _render_module_tree(branch: ModuleTree) -> str:
    items = []
    for part, children in sorted(branch.items()):
        label = f"<code>{_text(part)}</code>"
        items.append(
            f"<li><details><summary>{label}</summary>{_render_module_tree(children)}</details></li>"
            if children
            else f"<li>{label}</li>"
        )
    return f'<ul class="inventory-module-tree">{"".join(items)}</ul>'


def _module_tree_html(modules: list[str]) -> str:
    tree: ModuleTree = {}
    for module in modules:
        branch = tree
        for part in re.split(r"\.", module):
            if part not in branch:
                branch[part] = {}
            branch = branch[part]
    return _render_module_tree(tree)


def _compatibility_migration_work(observation: Observation) -> str:
    modules = sorted(
        {
            subject
            for record in observation.records("declarations") or ()
            if record.kind == "compatibility_migration_work"
            for subject in record.subjects
        }
    )
    if not modules:
        return ""
    return (
        '<section class="report-section"><h2>Compatibility migration work</h2>'
        f"<p>{len(modules)} migration shim(s) remain.</p>"
        f"{_module_tree_html(modules)}</section>"
    )


def _metadata(result: RunResult, observation: Observation | None) -> str:
    analyzer = observation.analyzer if observation is not None else None
    contract = observation.contract if observation is not None else None
    values = (
        ("Command", result.command),
        ("Exit code", result.exit_code),
        ("Analyzer", f"{analyzer.name} {analyzer.version}" if analyzer else "UNKNOWN"),
        ("Analyzer digest", analyzer.code_digest if analyzer else "UNKNOWN"),
        ("Python", result.python_version or "UNKNOWN"),
        ("Contract", contract.path if contract else "UNKNOWN"),
        ("Contract digest", contract.digest if contract else "UNKNOWN"),
    )
    rows = "".join(
        f"<tr><th>{_text(label)}</th><td><code>{_text(value)}</code></td></tr>"
        for label, value in values
    )
    return f'<div class="table-wrap"><table><tbody>{rows}</tbody></table></div>'


def _report_filters(
    observation: Observation,
    violations: tuple[Record, ...],
    assessments: tuple[RuleAssessment, ...] | None,
) -> str:
    kinds = sorted({item.kind for item in violations} | {item.kind for item in assessments or ()})
    components = sorted({label for label, _ in component_owners(observation)})

    def options(values: tuple[str, ...] | list[str]) -> str:
        return "".join(
            f'<option value="{_text(value)}">{_text(value)}</option>' for value in values
        )

    count = len(violations) + len(assessments or ())
    return f"""
    <form class="report-filters" data-report-filters aria-label="Filter report evidence" hidden>
      <label>Search rules and violations
        <input id="report-search" type="search" name="search" autocomplete="off">
      </label>
      <label>Kind<select id="report-kind" name="kind">
      <option value="">All kinds</option>{options(kinds)}</select>
      </label>
      <label>Component<select id="report-component" name="component">
      <option value="">All components</option>{options(components)}</select>
      </label>
      <label>Status<select id="report-status" name="status">
      <option value="">All statuses</option>{
        options(("PASS", "FAIL", "FAIL+UNKNOWN", "UNKNOWN", "DECLARATION"))
    }
      </select></label>
      <button type="reset">Reset filters</button>
      <output data-filter-count aria-live="polite">{count} rows</output>
    </form>"""


def _baseline_comparison(
    path: str | None,
    comparisons: tuple[BaselineViolationComparison, ...] | None,
) -> str:
    if path is None or comparisons is None:
        return ""
    rows = (
        "".join(
            "<tr>"
            f"<td><code>{_text(' '.join(item.rules))}</code></td>"
            f"<td><code>{_text(' · '.join(item.subjects))}</code></td>"
            f'<td class="numeric">{item.known_count}</td>'
            f'<td class="numeric">{item.current_count}</td>'
            f"<td>{_text(item.status.upper())}</td>"
            f"<td>{item.new_count} new · {item.resolved_count} resolved</td></tr>"
            for item in comparisons
        )
        or '<tr><td colspan="6">No violation fingerprints.</td></tr>'
    )
    return f"""
    <section class="report-section"><h2>Read-only baseline comparison</h2>
      <p>Baseline: <code>{_text(path)}</code>. Counts are grouped by fingerprint; repeated
      occurrences have no invented line identity. Resolved means absent under the currently
      evaluated rules, not proof the code was fixed: the baseline stores no prior rule definitions.
      Use <code>validate --against</code> to check contract changes.</p>
      <div class="table-wrap"><table><thead><tr><th>Rule</th><th>Subjects</th>
      <th>Known before</th><th>Current</th><th>Status</th><th>Drift</th></tr></thead>
      <tbody>{rows}</tbody></table></div>
    </section>"""


def render_html(
    result: RunResult,
    observation: Observation | None,
    *,
    repository: str,
    architecture_href: str | None,
) -> bytes:
    """Return a deterministic, offline HTML projection of one command result."""
    summary = report_summary(result)
    verdicts = "".join(_verdict_card(row) for row in summary.verdicts)
    diagnostics = "".join(_diagnostic(item) for item in result.diagnostics)
    if not diagnostics:
        diagnostics = "<p>None.</p>"
    failures = "".join(f"<li><code>{_text(item)}</code></li>" for item in result.failures)
    if not failures:
        # AD-100: --only calls draws its call table where the violations table would be.
        where = (
            "--only calls hides the declared-rule violations"
            if result.filtered_calls is not None
            else "see declared-rule violations below"
        )
        failures = (
            f"<li>Report mode does not evaluate an expectation; {where}.</li>"
            if report_violates_rules(result)
            else "<li>None.</li>"
        )
    # AD-60: a filtered run shows `filtered_violations`, the same records `ir.baseline
    # .select_violations` chose; an unfiltered one shows every violation, exactly as before.
    violations = (
        result.filtered_violations
        if result.report_filter is not None
        else observation.records("violations")
        if observation is not None
        else ()
    )
    unknowns = observation.records("unknowns") if observation is not None else ()
    source_sha = observation.source.git_head if observation is not None else "UNKNOWN"
    source_digest = observation.source.source_digest if observation is not None else "UNKNOWN"
    dirty = observation.source.dirty if observation is not None else "UNKNOWN"
    # AD-100: --only calls shows its call table in place of the violations table.
    calls_html = _calls(result.filtered_calls) if result.filtered_calls is not None else ""
    violations_html = (
        _violations(violations or (), observation, result.baseline_comparisons)
        if observation is not None and not calls_html
        else ""
    )
    rule_html = (
        _rule_assessments(result.rule_assessments)
        if not (
            result.report_filter is not None
            and (result.report_filter.only_violations or result.report_filter.only_calls)
        )
        else ""
    )
    filters_html = (
        _report_filters(
            observation,
            violations or (),
            result.rule_assessments,
        )
        if observation is not None and not calls_html
        else ""
    )
    baseline_html = _baseline_comparison(result.baseline_path, result.baseline_comparisons)
    # AD-60: --only violations hides everything below but the violations table, so a large
    # repository's page stays a small review surface instead of every section at once; --only
    # calls hides the same sections (AD-100). `focused` is either one.
    focused = result.report_filter is not None and (
        result.report_filter.only_violations or result.report_filter.only_calls
    )
    unknowns_html = (
        _findings("Known unknowns", unknowns or (), observation)
        if observation is not None and not focused
        else ""
    )
    migration_work_html = (
        _compatibility_migration_work(observation)
        if observation is not None and not focused
        else ""
    )
    flow_html = _flow_section(observation) if observation is not None and not focused else ""
    communication_html = (
        _interfaces_section(observation) if observation is not None and not focused else ""
    )
    interface_profile_html = (
        _interface_profile_section(observation) if observation is not None and not focused else ""
    )
    measurements_html = _measurements(result.measurements)
    coverage_html = _coverage(observation)
    structure_html = _structure(observation) if observation is not None and not focused else ""
    claims_html = _claims(observation) if observation is not None and not focused else ""
    inventory_html = _section_inventory(observation)
    metadata_html = _metadata(result, observation)
    raw_link = (
        f'<a href="{_text(architecture_href)}">Open canonical architecture.json</a>'
        if architecture_href is not None
        else "Canonical architecture.json is unavailable."
    )
    scope_note = (
        '<p class="report-scope"><strong>One repository snapshot.</strong> This report checks '
        "declared rules, not change against an earlier revision or runtime behavior. "
        f"{len(unknowns or ())} recorded analysis limits; "
        f"{observation.coverage.calls_unresolved} of "
        f"{observation.coverage.calls_analyzed} calls unresolved. "
        "These counts are not declared-rule violations.</p>"
        if observation is not None and not focused
        else ""
    )
    content = f"""
    <section class="report-heading">
      <span class="eyebrow">Repository observation</span>
      <h1>{_text(repository)}</h1>
      <div class="report-meta">
        <span>Candidate <strong>{_text(source_sha)}</strong></span>
        <span>Source <strong>{_text(source_digest)}</strong></span>
        <span>Dirty <strong>{_text(dirty)}</strong></span>
      </div>
    </section>
    <section class="decision-banner" data-decision="{summary.decision.state}"
             data-report-filter="{"true" if result.report_filter is not None else "false"}"
             aria-label="Decision: {summary.decision.label}">
      <span class="decision-symbol" aria-hidden="true">{summary.decision.symbol}</span>
      <div><h2>{summary.decision.label}</h2><p>{_text(summary.sentence)}</p></div>
    </section>
    <section aria-labelledby="verdicts-heading">
      <h2 id="verdicts-heading">Independent verdicts</h2>
      <div class="verdict-grid">{verdicts}</div>
    </section>
    {scope_note}
    <section class="report-section">
      <h2>Check evidence</h2>
      <h3>Failures</h3><ul class="failure-list">{failures}</ul>
      <h3>Diagnostics</h3><div class="diagnostic-list">{diagnostics}</div>
    </section>
    {flow_html}
    {filters_html}{violations_html}{rule_html}
    <script>{_asset("report-filters.js").decode("utf-8")}</script>
    {baseline_html}{calls_html}
    <div id="component-communication-detail" data-secondary-detail>{communication_html}</div>
    <div id="interface-profile-detail" data-secondary-detail>{interface_profile_html}</div>
    {unknowns_html}
    {migration_work_html}
    <details id="report-secondary-detail" data-secondary-detail
             class="report-section report-evidence">
      <summary>More measurements and review claims</summary>
      <section class="report-section"><h2>Measurements</h2>{measurements_html}</section>
      <section class="report-section"><h2>Coverage</h2>{coverage_html}</section>
      {structure_html}
      {claims_html}
    </details>
    <section class="report-section">
      <h2>Complete ArchitectureIR inventory</h2>
      <p>{raw_link}. The JSON remains the source for complete records and evidence.</p>
      {inventory_html}
    </section>
    <section class="report-section">
      <h2>Reproduction metadata</h2>
      {metadata_html}
    </section>
"""
    return _document(
        repository=repository,
        kind="Architecture evidence report",
        title="Archkeel report",
        content=content,
    )


def _regressions(comparisons: tuple[Comparison, ...]) -> str:
    if not comparisons:
        return "<p>Regression measurements are unavailable.</p>"
    rows = "".join(
        "<tr>"
        f"<td><code>{_text(name)}</code></td>"
        f'<td class="numeric"><code>{_text(accepted)} → {_text(candidate)}</code></td>'
        f'<td><strong data-status="{badge(status).state}">{status}</strong></td>'
        "</tr>"
        for name, accepted, candidate, status in comparisons
    )
    return (
        '<div class="table-wrap"><table class="regression-table"><thead><tr><th>Measurement</th>'
        '<th class="numeric">Accepted → candidate</th><th>Status</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def _semantic_changes(result: RunResult) -> str:
    changes = result.delta.semantic_changes if result.delta is not None else ()
    if not changes:
        return "<p>No semantic changes were observed.</p>"
    rows = "".join(
        "<tr>"
        f"<td><code>{_text(item.dimension)}</code></td>"
        f"<td>{_text(item.change)}</td>"
        f'<td class="numeric">{item.before_count} → {item.after_count}</td>'
        f"<td><code>{_text(item.fingerprint)}</code></td>"
        "</tr>"
        for item in changes
    )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Dimension</th>'
        '<th>Observed change</th><th class="numeric">Before → after</th>'
        f"<th>Fingerprint</th></tr></thead><tbody>{rows}</tbody></table></div>"
    )


def render_check_html(result: RunResult, *, repository: str, result_href: str) -> bytes:
    """Return a deterministic, offline projection of a check result."""
    summary = check_summary(result)
    verdicts = "".join(_verdict_card(row) for row in summary.verdicts)
    host_order = result.host_order or "UNKNOWN"
    provenance = result.provenance
    accepted = provenance.baseline if provenance else "UNKNOWN"
    candidate = provenance.head if provenance else "UNKNOWN"
    failures = "".join(f"<li><code>{_text(item)}</code></li>" for item in result.failures)
    diagnostics = "".join(_diagnostic(item) for item in result.diagnostics)
    content = f"""
    <section class="report-heading">
      <span class="eyebrow">Candidate check</span><h1>{_text(repository)}</h1>
      <div class="report-meta"><span>Accepted <strong>{_text(accepted)}</strong></span>
        <span>Candidate <strong>{_text(candidate)}</strong></span>
        <span>Host source <strong>{_text(result.host_source or "UNKNOWN")}</strong></span></div>
    </section>
    <section class="decision-banner" data-decision="{summary.decision.state}"
             aria-label="Decision: {summary.decision.label}">
      <span class="decision-symbol" aria-hidden="true">{summary.decision.symbol}</span><div>
        <h2>{summary.decision.label}</h2><p>{_text(summary.sentence)}</p></div>
    </section>
    <section aria-labelledby="verdicts-heading">
      <h2 id="verdicts-heading">Independent verdicts</h2><div
        class="verdict-grid verdict-grid-check">{verdicts}</div></section>
    <section class="report-section"><h2>Regression checks</h2>{_regressions(summary.regressions)}
    </section>
    <section class="report-section">
      <h2>Publication order evidence</h2><p>Status:
        <strong data-status="{badge(host_order).state}">
        {_text(host_order)}</strong></p></section>
    <section class="report-section"><h2>Failures</h2>
      <ul class="failure-list">{failures or "<li>None.</li>"}</ul></section>
    <section class="report-section">
      <h2>Declared and observed changes</h2>
      <p>The check compared these observed changes with the published declaration.</p>{
        _semantic_changes(result)
    }</section>
    <section class="report-section"><h2>Diagnostics</h2><div class="diagnostic-list">{
        diagnostics or "<p>None.</p>"
    }</div></section>
    <section class="report-section">
      <h2>Canonical result</h2><p><a href="{_text(result_href)}">Open the check result JSON</a>.</p>
    </section>
"""
    return _document(
        repository=repository,
        kind="Architecture check report",
        title="Archkeel check",
        content=content,
    )


def _structure_row(metric: StructureMetric) -> str:
    share = f"{metric.unresolved} of {metric.calls}" if metric.calls else "no calls"
    return (
        f"<tr><td><code>{_text(metric.scope)}</code></td><td>{_text(metric.level)}</td>"
        f'<td class="numeric">{metric.modules}</td>'
        f'<td class="numeric">{metric.inner_edges}</td>'
        f'<td class="numeric">{metric.fan_in}</td>'
        f'<td class="numeric">{metric.fan_out}</td>'
        f'<td class="numeric">{_text(share)}</td></tr>'
    )


def _claim_body(claim: SymbolReferences, observation: Observation) -> str:
    if claim.status == "UNKNOWN":
        return (
            "<p>Not available: this observation carries no reference signal, so a call graph "
            "alone would report every symbol that is only handed to a table as unreferenced.</p>"
        )
    coverage = observation.coverage
    share = (
        f"{coverage.calls_unresolved} of {coverage.calls_analyzed} calls stay unresolved"
        if coverage.calls_analyzed
        else "no calls analyzed"
    )
    if not claim.candidates:
        return (
            f"<p>None: every one of {claim.symbols} symbols is named somewhere, and "
            f"{claim.exempt} were set aside as runtime dispatch or declared interface. {share}.</p>"
        )
    rows = "".join(
        f"<tr><td><code>{_text(item.name)}</code></td><td>{_text(item.kind)}</td>"
        f"<td>{_text(item.visibility)}</td></tr>"
        for item in claim.candidates
    )
    return f"""
      <p>{len(claim.candidates)} of {claim.symbols} symbols are named by no call, reference or
      import inside the scan scope; {claim.exempt} were set aside as runtime dispatch or declared
      interface. A consumer outside the scan scope, such as a test, is invisible here, and {share},
      so these are candidates for review, never a verdict.</p>
      <table class="data-table"><thead><tr><th>Symbol</th><th>Kind</th><th>Visibility</th></tr>
      </thead><tbody>{rows}</tbody></table>
"""


def _binding_claim_body(claim: BindingReads) -> str:
    if claim.status == "UNKNOWN":
        return (
            "<p>Not available: this observation carries no binding signal, so nothing here can "
            "list which parameter or local the collector found unread.</p>"
        )
    if not claim.candidates:
        return (
            f"<p>None recorded: no unread-binding candidates across {claim.functions} functions "
            "and methods. This does not establish that every unlisted binding is read; removal "
            "safety is not assessed.</p>"
        )
    rows = "".join(
        f"<tr><td><code>{_text(item.owner)}</code></td><td><code>{_text(item.name)}</code></td>"
        f"<td>{_text(item.binding)}</td></tr>"
        for item in claim.candidates
    )
    return f"""
      <p>Code in these functions does not read the listed names ({len(claim.candidates)}). A
      parameter may still be required by an interface; review before removing it.</p>
      <table class="data-table"><thead><tr><th>Function</th><th>Name</th><th>Binding</th></tr>
      </thead><tbody>{rows}</tbody></table>
"""


def _repetition_claim_body(claim: OwnedLogic) -> str:
    if claim.status == "UNKNOWN":
        return (
            "<p>Not available: this observation carries no shape signal, so nothing here can say "
            "which function repeats another.</p>"
        )
    if not claim.owners:
        return (
            f"<p>Not claimed: no spot_owner is declared, so none of the {claim.functions} "
            "functions and methods has an owner to repeat.</p>"
        )
    if not claim.candidates:
        return (
            f"<p>None: across {claim.functions} functions and methods, nothing outside the "
            f"{claim.owners} declared owners repeats the structure of anything inside them.</p>"
        )
    rows = "".join(
        f"<tr><td><code>{_text(item.outside)}</code></td><td><code>{_text(item.inside)}</code></td>"
        f"<td><code>{_text(item.owner)}</code></td>"
        f'<td class="numeric">{item.shape_nodes}</td></tr>'
        for item in claim.candidates
    )
    return f"""
      <p>{len(claim.candidates)} functions outside a declared owner have the same structure as a
      function inside it, names and literals aside. Only exact structural twins of at least
      {MINIMUM_SHAPE_NODES} nodes count, so a shape the language forces is not reported. What the
      repetition means is the architect's to decide, never a verdict.</p>
      <table class="data-table"><thead><tr><th>Outside</th><th>Repeats</th><th>Declared owner</th>
      <th class="numeric">Nodes</th></tr></thead><tbody>{rows}</tbody></table>
"""


def _fanin_claim_body(claim: TypeFanin) -> str:
    if claim.status == "UNKNOWN":
        return (
            "<p>Not available: this observation carries no symbols or imports section, so "
            "nothing here can say which type crosses which component boundary.</p>"
        )
    if not claim.candidates:
        return (
            f"<p>None: across {claim.positions} annotated positions on functions and methods "
            f"crossing a component boundary, nothing is passed across {MINIMUM_CROSSINGS} or "
            "more distinct component pairs.</p>"
        )
    rows = "".join(
        f"<tr><td><code>{_text(item.annotation)}</code></td>"
        f'<td class="numeric">{item.crossings}</td></tr>'
        for item in claim.candidates
    )
    return f"""
      <p>{len(claim.candidates)} of {claim.positions} annotated positions on functions and
      methods crossing a component boundary name a type passed across {MINIMUM_CROSSINGS} or
      more distinct component pairs. A broad context or a service locator shows up as a wide
      count here; what it means is the architect's to decide, never a verdict.</p>
      <table class="data-table"><thead><tr><th>Type</th>
      <th class="numeric">Component pairs</th></tr></thead><tbody>{rows}</tbody></table>
"""


def _inside_claim_body(claim: InsideSizes) -> str:
    if claim.status == "UNKNOWN":
        return (
            "<p>UNKNOWN: this observation records no modules or no dependency edges, so no "
            "inside can be measured against the level that holds it.</p>"
        )
    scale = (
        f"The top level holds {claim.components} components and {claim.component_edges} edges "
        "between them."
    )
    if not claim.candidates:
        return f"<p>None: no component holds more than the level containing it. {scale}</p>"
    rows = "".join(
        f"<tr><td>{_text(item.scope)}</td><td>{item.modules}</td><td>{item.inner_edges}</td></tr>"
        for item in claim.candidates
    )
    return f"""
      <p>{len(claim.candidates)} components hold more modules than the contract has components,
      or more edges among their modules than it has component edges. {scale} Naming a size is
      evidence; giving one of them a level of its own is a decision (AD-20, AD-33).</p>
      <table class="data-table"><thead><tr><th>Component</th><th>Modules</th>
      <th>Edges inside</th></tr></thead><tbody>{rows}</tbody></table>
"""


def _claims(observation: Observation) -> str:
    """AD-26: every Class D claim, shown with its support and never turned into a verdict."""
    return f"""
    <section class="report-section">
      <h2>Review claim: symbols nobody references</h2>
      {_claim_body(unreferenced_symbols(observation), observation)}
    </section>
    <section class="report-section">
      <h2>Review claim: components larger than their level</h2>
      {_inside_claim_body(oversized_insides(observation))}
    </section>
    <section class="report-section">
      <h2>Review candidates: unread parameters and locals</h2>
      {_binding_claim_body(unread_bindings(observation))}
    </section>
    <section class="report-section">
      <h2>Review claim: logic repeated outside its owner</h2>
      {_repetition_claim_body(repeated_logic(observation))}
    </section>
    <section class="report-section">
      <h2>Review claim: types crossing the most component boundaries</h2>
      {_fanin_claim_body(type_fanin(observation))}
    </section>
"""


def _structure(observation: Observation) -> str:
    """AD-21: size and coupling per scope, shown and never gated on."""
    metrics = structure_metrics(observation)
    if not metrics:
        return ""
    rows = "".join(_structure_row(metric) for metric in metrics)
    return f"""
    <section class="report-section">
      <h2>Size and coupling</h2>
      <p>Measured per component and per package: how many modules a scope holds, how many
      imports stay inside it, how many cross its edge, and how many of its calls the analyzer
      could not resolve. These numbers are shown, never gated on.</p>
      <table class="data-table"><thead><tr><th>Scope</th><th>Level</th><th>Modules</th>
      <th>Inside</th><th>Incoming</th><th>Outgoing</th><th>Unresolved calls</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </section>
"""


def render_architecture_html(
    result: RunResult,
    architecture_json: bytes,
    *,
    repository: str,
    architecture_href: str,
) -> bytes:
    """Render a report result with its canonical observation artifact.

    Derives the agent-decisions count and the open decisions from these bytes, never from
    `result`, so a report rendered later from `architecture.json` alone still shows both
    (AD-16, AD-23).
    """
    observation = parse_observation(decode_canonical_model(json.loads(architecture_json)))
    return render_html(
        replace(
            result,
            agent_decisions=agent_decisions(observation),
            open_decisions=open_decisions(observation),
        ),
        observation,
        repository=repository,
        architecture_href=architecture_href,
    )
