# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Render a portable evidence report without changing check semantics."""

from __future__ import annotations

import base64
import html
import json
from dataclasses import replace
from importlib.resources import files

from archkeel.ir.bindings import BindingReads, unread_bindings
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import agent_decisions, open_decisions
from archkeel.ir.duplication import MINIMUM_SHAPE_NODES, OwnedLogic, repeated_logic
from archkeel.ir.interfaces import (
    InterfaceEdge,
    InterfaceName,
    interface_edges,
    interface_profile,
)
from archkeel.ir.measurements import Measurements
from archkeel.ir.model import CallRow, Diagnostic, Observation, Record, RunResult
from archkeel.ir.references import SymbolReferences, unreferenced_symbols
from archkeel.ir.structure import (
    InsideSizes,
    StructureMetric,
    oversized_insides,
    structure_metrics,
)
from archkeel.ir.type_fanin import MINIMUM_CROSSINGS, TypeFanin, type_fanin

from .flow import FlowData, FlowInnerEdge, FlowInside, build_flow
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
      <h2>{_text(title)}</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Fingerprint</th><th>Finding</th><th>Subjects</th><th>Evidence</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>"""


def _violations(items: tuple[Record, ...], observation: Observation) -> str:
    """Render a local violations-only view without changing the CLI-selected records."""
    if not items:
        return (
            '<section class="report-section"><h2>Declared-rule violations</h2>'
            "<p>None.</p></section>"
        )
    rows = "".join(_record_row(item, observation) for item in items)
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
          <thead><tr><th>Fingerprint</th><th>Finding</th><th>Subjects</th><th>Evidence</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      <script>{script}</script>
    </section>"""


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
    names = "<br>".join(_interface_name_line(item) for item in edge.names)
    return (
        "<tr>"
        f"<td><code>{_text(edge.source)} → {_text(edge.target)}</code></td>"
        f'<td class="numeric">{len(edge.names)}</td>'
        f"<td>{names}</td>"
        "</tr>"
    )


def _interfaces_section(observation: Observation) -> str:
    edges = interface_edges(observation)
    if not edges:
        body = "<p>No cross-component imports were observed.</p>"
    else:
        rows = "".join(_interface_edge_row(edge) for edge in edges)
        body = (
            '<div class="table-wrap"><table><thead><tr><th>Edge</th>'
            '<th class="numeric">Names</th><th>Interface</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>"
        )
    return f'<section class="report-section"><h2>Component communication</h2>{body}</section>'


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
      <h2>Declared facade measurements</h2>
      <p>Observed from declared facades and imports: exported-name count, re-exports, names
      defined in the facade, unused re-exports, consumers per exported name and coupling width.
      They do not claim a barrel is complete (AD-88); <code>validate</code> holds declared
      facade and coupling budgets to them (AD-99).</p>
      <h3>Facades</h3>
      <div class="table-wrap"><table><thead><tr><th>Component</th><th>Module</th>
      <th class="numeric">Exports</th><th class="numeric">Re-exports</th><th>Defined</th>
      <th>Unused re-exports</th></tr></thead><tbody>{facade_rows}</tbody></table></div>
      <h3>Export consumers</h3>
      <div class="table-wrap"><table><thead><tr><th>Component</th><th>Export</th>
      <th class="numeric">Consumers</th><th>Components</th></tr></thead>
      <tbody>{usage_rows}</tbody></table></div>
      <h3>Coupling width</h3>
      <div class="table-wrap"><table><thead><tr><th>Component pair</th>
      <th class="numeric">Distinct names</th><th>Names</th></tr></thead>
      <tbody>{coupling_rows}</tbody></table></div>
    </section>
    """


def _within(qualified: str, module: str) -> str:
    """Drop the module prefix a payload key already carries."""
    return qualified[len(module) + 1 :] if qualified.startswith(f"{module}.") else qualified


def _inner_edge_payload(edges: tuple[FlowInnerEdge, ...]) -> list[dict[str, object]]:
    return [
        {
            "source": edge.source,
            "target": edge.target,
            "import_sites": edge.import_sites,
            "rule_ids": list(edge.rule_ids),
            "state": edge.state,
        }
        for edge in edges
    ]


def _inside_payload(inside: FlowInside | None) -> dict[str, object] | None:
    """Serialise a declared inside the way `level()` consumes it, or None when none exists."""
    if inside is None:
        return None
    return {
        "components": [
            {
                "label": card.label,
                "modules": list(card.modules),
                "public": list(card.public) if card.public is not None else None,
                "inner_edges": _inner_edge_payload(card.inner_edges),
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
            }
            for edge in inside.edges
        ],
        "unassigned": list(inside.unassigned),
    }


def _flow_payload(observation: Observation, flow: FlowData) -> dict[str, object]:
    names_by_pair = {
        (edge.source, edge.target): edge.names for edge in interface_edges(observation)
    }
    return {
        "components": [
            {
                "label": component.label,
                "modules": list(component.modules),
                "public": list(component.public) if component.public is not None else None,
                "inner_edges": _inner_edge_payload(component.inner_edges),
                "inside": _inside_payload(component.inside),
            }
            for component in flow.components
        ],
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "import_sites": edge.import_sites,
                "rule_ids": list(edge.rule_ids),
                "state": edge.state,
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
            for edge in flow.edges
        ],
        # Symbol names are stored relative to the module that keys them: the prefix is already
        # the key, and repeating it on 466 cards and both ends of 596 edges tripled the payload.
        "modules": {
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
        },
    }


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
      <p>Component cards and the observed edges between them. Every edge is drawn at one
        width and carries a label: the rule it breaks, or the number of import sites that
        cross it. An arrow and a travelling pulse run from the importer to the imported. Red
        breaks a declared rule and the label names it; teal conforms; amber is undecided, a
        decision the contract still owes; grey is observed inside a component, where none is
        owed (AD-24b). This view needs JavaScript; the table below lists the same crossings
        for print and no-script use.</p>
      <div id="flow" class="flow">
        <div class="flow-toolbar">
          <label class="flow-violation-focus" for="flow-violations-only" hidden>
            <input id="flow-violations-only" class="flow-violations-only" type="checkbox"
                   aria-controls="flow-graph">
            Violating edges only
          </label>
          <label for="flow-threshold-input">Hide edges below
            <output id="flow-threshold-value" class="flow-threshold-value">≥ 0 import sites</output>
          </label>
          <input id="flow-threshold-input" class="flow-threshold" type="range" min="0" value="0">
          <button type="button" class="flow-back" hidden>Back to components</button>
          <button type="button" class="flow-fit"
            title="Lay the cards out again and fit them into view">Arrange</button>
        </div>
        <div class="flow-canvas">
          <svg id="flow-graph" class="flow-graph" role="group"
               aria-label="Component flow diagram">
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
          </svg>
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
    return (
        '<div class="table-wrap"><table><thead><tr><th>ArchitectureIR section</th>'
        f'<th class="numeric">Records</th></tr></thead><tbody>{rows}</tbody></table></div>'
    )


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
    items = "".join(f"<li><code>{_text(module)}</code></li>" for module in modules)
    return (
        '<section class="report-section"><h2>Compatibility migration work</h2>'
        f"<p>{len(modules)} migration shim(s) remain.</p><ul>{items}</ul></section>"
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
        _violations(violations or (), observation)
        if observation is not None and not calls_html
        else ""
    )
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
    <section class="report-section">
      <h2>Check evidence</h2>
      <h3>Failures</h3><ul class="failure-list">{failures}</ul>
      <h3>Diagnostics</h3><div class="diagnostic-list">{diagnostics}</div>
    </section>
    {violations_html}{calls_html}
    {flow_html}
    <div id="component-communication-detail" data-secondary-detail>{communication_html}</div>
    <div id="interface-profile-detail" data-secondary-detail>{interface_profile_html}</div>
    {unknowns_html}
    {migration_work_html}
    <div id="report-secondary-detail" data-secondary-detail>
      <section class="report-section"><h2>Measurements</h2>{measurements_html}</section>
      <section class="report-section"><h2>Coverage</h2>{coverage_html}</section>
      {structure_html}
      {claims_html}
    </div>
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
