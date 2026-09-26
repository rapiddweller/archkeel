# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep unread-binding evidence distinct from proof that an unread parameter is removable."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from test_analyzer import _observe

from archkeel.ir.bindings import unread_bindings
from archkeel.render.html import _binding_claim_body


def _observe_source(tmp_path: Path, source: str):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "ports.py").write_text(source)
    result = _observe(tmp_path)
    assert result.observation is not None
    return result.observation


def test_protocol_signature_is_not_reported_as_every_parameter_read(tmp_path: Path) -> None:
    observation = _observe_source(
        tmp_path,
        """from typing import Protocol

class Exporter(Protocol):
    def export(self, context: _SmokeExporterContext) -> None: ...
""",
    )

    claim = unread_bindings(observation)
    body = _binding_claim_body(claim)

    assert "context" in body or "_SmokeExporterContext" in body
    assert "every parameter and local is read" not in body
    assert "not assessed" in body.lower() or "unknown" in body.lower()


def test_lexical_unread_parameters_remain_candidates_but_reads_do_not(tmp_path: Path) -> None:
    observation = _observe_source(
        tmp_path,
        """def left(unused, shared):
    return shared

def right(shared, unused):
    return shared
""",
    )

    claim = unread_bindings(observation)
    named = [(item.owner, item.name, item.binding) for item in claim.candidates]
    body = _binding_claim_body(claim)

    assert claim.status == "SUPPORTED"
    assert named == [
        ("sample.ports.left", "unused", "parameter"),
        ("sample.ports.right", "unused", "parameter"),
    ]
    evidence_ids = {
        evidence_id
        for record in observation.records("bindings") or ()
        for evidence_id in record.evidence_ids
    }
    assert evidence_ids
    assert evidence_ids <= {item.id for item in observation.evidence}
    assert "shared" not in body
    assert "candidates for review, never a verdict" in body


def test_missing_binding_signal_is_unknown_not_an_empty_supported_claim(tmp_path: Path) -> None:
    observation = _observe_source(
        tmp_path,
        """from typing import Protocol

class Exporter(Protocol):
    def export(self, context: _SmokeExporterContext) -> None: ...
""",
    )
    without_signal = replace(
        observation,
        sections=tuple(section for section in observation.sections if section.name != "bindings"),
    )

    unknown = unread_bindings(without_signal)
    supported_empty = unread_bindings(observation)

    assert unknown.status == "UNKNOWN"
    assert "Not available" in _binding_claim_body(unknown)
    assert supported_empty.status == "SUPPORTED"
    assert "every parameter and local is read" not in _binding_claim_body(supported_empty)
