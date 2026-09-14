# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Render a portable evidence report without changing check semantics."""

from __future__ import annotations

import base64
import html
from importlib.resources import files

from archkeel.ir.measurements import Measurements
from archkeel.ir.model import Diagnostic, Observation, Record, RunResult


def _asset(name: str) -> bytes:
    return files("archkeel.check").joinpath("assets", name).read_bytes()


def _data_uri(name: str, mime_type: str) -> str:
    encoded = base64.b64encode(_asset(name)).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _text(value: object) -> str:
    return html.escape(str(value), quote=True)


def _verdict(value: str) -> tuple[str, str, str]:
    if value == "PASS":
        return "pass", "✓", "PASS"
    if value == "FAIL":
        return "fail", "×", "FAIL"
    if value == "n/a":
        return "info", "i", "NOT APPLICABLE"
    return "unknown", "?", "UNVERIFIABLE"


def _decision(result: RunResult) -> tuple[str, str, str, str]:
    if result.exit_code == 0:
        return "pass", "✓", "PASS", "All requested deterministic checks completed."
    if result.exit_code == 1:
        return "fail", "×", "REJECT", "One or more deterministic checks rejected the candidate."
    return (
        "unknown",
        "?",
        "UNVERIFIABLE",
        "Required evidence is missing or invalid; no pass decision was made.",
    )


def _verdict_card(key: str, value: str, reason: str) -> str:
    state, symbol, label = _verdict(value)
    return f"""
      <article class="verdict-card" data-verdict="{state}">
        <div class="verdict-state"><span aria-hidden="true">{symbol}</span>{label}</div>
        <h3><code>{_text(key)}</code></h3>
        <p>{_text(reason)}</p>
      </article>"""


def _diagnostic(item: Diagnostic) -> str:
    fields = (
        ("kind", item.kind),
        ("subject", item.subject),
        ("unknown_claim", item.unknown_claim),
        ("remedy", item.remedy),
    )
    values = "".join(f"<dt>{name}</dt><dd>{_text(value)}</dd>" for name, value in fields)
    return f'<dl class="diagnostic">{values}</dl>'


def _record_row(item: Record, observation: Observation) -> str:
    evidence = {entry.id: entry for entry in observation.evidence}
    location = ""
    if item.evidence_ids:
        source = evidence.get(item.evidence_ids[0])
        if source is not None:
            location = f"{source.file}:{source.line}"
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


def _measurements(measurements: Measurements | None) -> str:
    if measurements is None:
        return "<p>No complete measurements are available.</p>"
    rows = "".join(
        f'<tr><td><code>{_text(name)}</code></td><td class="numeric">{value}</td></tr>'
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
    css = _asset("archkeel-report.css").decode("utf-8")
    dark_logo = _data_uri("archkeel-logo-dark.svg", "image/svg+xml")
    light_logo = _data_uri("archkeel-logo-light.svg", "image/svg+xml")
    mark = _data_uri("archkeel-mark.svg", "image/svg+xml")
    decision, symbol, label, reason = _decision(result)
    observation_reason = (
        "All configured source files were read and parsed."
        if result.observation_complete == "PASS"
        else "The configured source scope could not be observed completely."
    )
    rules_reason = {
        "PASS": "No declared-rule violation was found.",
        "FAIL": "At least one declared rule was violated.",
        "UNKNOWN": "Declared rules could not be evaluated completely.",
    }[result.declared_rules]
    expectation_reason = {
        "PASS": "The candidate matches its published expectation.",
        "FAIL": "The candidate does not match its published expectation.",
        "UNKNOWN": "The expectation could not be evaluated completely.",
        "n/a": "Report mode does not evaluate a published expectation.",
    }[result.expectation_fulfilled]
    verdicts = "".join(
        (
            _verdict_card("observation_complete", result.observation_complete, observation_reason),
            _verdict_card("declared_rules", result.declared_rules, rules_reason),
            _verdict_card(
                "expectation_fulfilled", result.expectation_fulfilled, expectation_reason
            ),
        )
    )
    diagnostics = "".join(_diagnostic(item) for item in result.diagnostics)
    if not diagnostics:
        diagnostics = "<p>None.</p>"
    failures = "".join(f"<li><code>{_text(item)}</code></li>" for item in result.failures)
    if not failures:
        failures = "<li>None.</li>"
    violations = observation.records("violations") if observation is not None else ()
    unknowns = observation.records("unknowns") if observation is not None else ()
    source_sha = observation.source.git_head if observation is not None else "UNKNOWN"
    source_digest = observation.source.source_digest if observation is not None else "UNKNOWN"
    dirty = observation.source.dirty if observation is not None else "UNKNOWN"
    violations_html = (
        _findings("Declared-rule violations", violations or (), observation)
        if observation is not None
        else ""
    )
    unknowns_html = (
        _findings("Known unknowns", unknowns or (), observation) if observation is not None else ""
    )
    measurements_html = _measurements(result.measurements)
    coverage_html = _coverage(observation)
    inventory_html = _section_inventory(observation)
    metadata_html = _metadata(result, observation)
    raw_link = (
        f'<a href="{_text(architecture_href)}">Open canonical architecture.json</a>'
        if architecture_href is not None
        else "Canonical architecture.json is unavailable."
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
  <link rel="icon" href="{mark}" type="image/svg+xml">
  <title>Archkeel report · {_text(repository)}</title>
  <style>{css}</style>
</head>
<body>
  <header class="report-header">
    <img class="report-logo report-logo-dark" src="{dark_logo}" alt="Archkeel">
    <img class="report-logo report-logo-light" src="{light_logo}" alt="Archkeel">
    <span class="report-kind">Architecture evidence report</span>
  </header>
  <main class="report-shell">
    <section class="report-heading">
      <span class="eyebrow">Repository observation</span>
      <h1>{_text(repository)}</h1>
      <div class="report-meta">
        <span>Candidate <strong>{_text(source_sha)}</strong></span>
        <span>Source <strong>{_text(source_digest)}</strong></span>
        <span>Dirty <strong>{_text(dirty)}</strong></span>
      </div>
    </section>
    <section class="decision-banner" data-decision="{decision}" aria-label="Decision: {label}">
      <span class="decision-symbol" aria-hidden="true">{symbol}</span>
      <div><h2>{label}</h2><p>{_text(reason)}</p></div>
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
    {violations_html}
    {unknowns_html}
    <section class="report-section"><h2>Measurements</h2>{measurements_html}</section>
    <section class="report-section"><h2>Coverage</h2>{coverage_html}</section>
    <section class="report-section">
      <h2>Complete ArchitectureIR inventory</h2>
      <p>{raw_link}. The JSON remains the source for complete records and evidence.</p>
      {inventory_html}
    </section>
    <section class="report-section">
      <h2>Reproduction metadata</h2>
      {metadata_html}
    </section>
    <footer class="report-footer">Archkeel · deterministic architecture evidence</footer>
  </main>
</body>
</html>
"""
    return document.encode("utf-8")
