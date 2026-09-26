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


def test_ce_smoke_context_unread_parameters_remain_visible_without_removal_claim(
    tmp_path: Path,
) -> None:
    observation = _observe_source(
        tmp_path,
        """from typing import Protocol

class Client:
    pass

class ExporterContext(Protocol):
    def get_client_by_id(self, client_id: str) -> Client | None: ...
    def contain(self, memstore_id: str) -> bool: ...

class _SmokeExporterContext:
    def get_client_by_id(self, client_id: str) -> Client | None:
        return None

    def contain(self, memstore_id: str) -> bool:
        return False

context: ExporterContext = _SmokeExporterContext()
""",
    )

    claim = unread_bindings(observation)
    body = _binding_claim_body(claim)
    named = [(item.owner, item.name) for item in claim.candidates]

    assert named == [
        ("sample.ports._SmokeExporterContext.contain", "memstore_id"),
        ("sample.ports._SmokeExporterContext.get_client_by_id", "client_id"),
    ]
    assert "client_id" in body and "memstore_id" in body
    assert "review before removing it" in body.lower()
    assert "safe to remove" not in body.lower()


def test_protocol_stub_empty_claim_does_not_assert_every_parameter_is_read(
    tmp_path: Path,
) -> None:
    observation = _observe_source(
        tmp_path,
        """from typing import Protocol

class ExporterContext(Protocol):
    def get_client_by_id(self, client_id: str) -> object | None: ...
    def contain(self, memstore_id: str) -> bool: ...
""",
    )

    claim = unread_bindings(observation)
    body = _binding_claim_body(claim)

    assert claim.status == "SUPPORTED"
    assert claim.candidates == ()
    assert "every parameter and local is read" not in body
    assert "not assessed" in body.lower() or "unknown" in body.lower()


def test_same_named_and_ordinary_unread_parameters_keep_lexical_evidence(
    tmp_path: Path,
) -> None:
    observation = _observe_source(
        tmp_path,
        """def left(unused, shared):
    return shared

def right(unused):
    return unused

def ordinary(plain_unused, value):
    return value
""",
    )

    claim = unread_bindings(observation)
    named = [(item.owner, item.name, item.binding) for item in claim.candidates]
    body = _binding_claim_body(claim)

    assert claim.status == "SUPPORTED"
    assert named == [
        ("sample.ports.left", "unused", "parameter"),
        ("sample.ports.ordinary", "plain_unused", "parameter"),
    ]
    evidence_ids = {
        evidence_id
        for record in observation.records("bindings") or ()
        for evidence_id in record.evidence_ids
    }
    assert evidence_ids
    assert evidence_ids <= {item.id for item in observation.evidence}
    assert all(name not in body for name in ("shared", "value", "right"))
    assert "safe to remove" not in body.lower()


def test_missing_binding_signal_is_unknown_not_an_empty_supported_claim(tmp_path: Path) -> None:
    observation = _observe_source(
        tmp_path,
        """from typing import Protocol

class ExporterContext(Protocol):
    def get_client_by_id(self, client_id: str) -> object | None: ...
    def contain(self, memstore_id: str) -> bool: ...
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
