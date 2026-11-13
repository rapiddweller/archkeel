# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A Python runtime name is not proof of a Python analyzer identity."""

from types import SimpleNamespace

import pytest

from archkeel.ir.dependency_binding import dependency_runtime_identity, dependency_runtime_rejection
from archkeel.ir.facts import AnalyzerInfo, RuntimeInfo, RuntimeRequirementState
from archkeel.ir.languages import SourceProfile
from archkeel.ir.model import RecordData
from archkeel.ir.state_facts import ProducerKind, VerifiedBinary


@pytest.mark.parametrize(
    "producer", [ProducerKind.PYTHON, ProducerKind.EXTERNAL, ProducerKind.PINNED]
)
@pytest.mark.parametrize("profile", list(SourceProfile))
def test_python_lower_bound_requires_python_analyzer_identity(producer, profile):
    observation = SimpleNamespace(
        analyzer=AnalyzerInfo(profile, "0.0.0", "0" * 64),
        runtime=RuntimeInfo("python", "3.11.12", ">=3.11", RuntimeRequirementState.DECLARED),
        producer_kind=producer,
        verified_binary=None,
    )
    rejected = dependency_runtime_rejection(observation, RecordData(()))
    assert rejected == (
        None if profile is SourceProfile.PYTHON else "dependency_scope_runtime_unverified"
    )


@pytest.mark.parametrize("digest", [None, "sha256:" + "1" * 64, "sha256:" + "0" * 64])
def test_native_scope_requires_this_runs_verified_digest(digest):
    binary = VerifiedBinary("sha256:" + "0" * 64)
    runtime = RuntimeInfo("rust", "1.97.0", None, RuntimeRequirementState.REQUIREMENT_MISSING)
    observation = SimpleNamespace(
        producer_kind=ProducerKind.BUNDLED,
        verified_binary=binary,
        runtime=runtime,
    )
    proof = RecordData(
        (("runtime", RecordData(() if digest is None else (("code_digest", digest),))),)
    )
    assert dependency_runtime_rejection(observation, proof) == (
        "dependency_scope_runtime_digest_missing"
        if digest is None
        else "dependency_scope_runtime_digest_mismatch"
        if digest != binary.digest
        else None
    )
    assert dependency_runtime_identity(runtime, binary).get("code_digest") == binary.digest
