# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Real Git/check composition with explicitly simulated causal host evidence."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_result_schema import validator as validator

from archkeel.analyzer import observe
from archkeel.check.run import run_check
from archkeel.ir.codec import result_payload
from archkeel.ir.host_records import InitialPRHeadEvidence, OrderingError
from archkeel.render.html import render_check_html
from fixtures.demo_catalog_check import _COMMENT_ONLY_FILES, CONFIG, build_and_run_check


@pytest.fixture
def protocol(tmp_path: Path):
    result = build_and_run_check(tmp_path, _COMMENT_ONLY_FILES, "empty_declaration")
    assert result.provenance is not None
    source = result.provenance
    proof = InitialPRHeadEvidence(
        "fixture/local",
        7,
        11,
        13,
        17,
        source.expectation,
        source.head,
        "2026-01-01T10:00:00Z",
        source.baseline,
        19,
        23,
        "a" * 64,
        "f" * 64,
    )
    return tmp_path / "root", source, proof


def check(protocol, proof):
    root, source, _ = protocol
    return run_check(
        root,
        config=CONFIG,
        baseline=source.baseline,
        expectation_commit=source.expectation,
        head=source.head,
        expected_path="expectation.json",
        expected_digest=source.expected_digest,
        branch="candidate",
        accepted_branch="main",
        host_records_path=None,
        environ={},
        host=lambda *args, **kwargs: proof,
        analyzer=observe,
    )


def test_causal_check_reobserves_the_lock_and_keeps_host_provenance(protocol) -> None:
    result = check(protocol, protocol[2])
    assert (result.exit_code, result.git_predicate, result.host_order) == (0, "PASS", "PASS")
    assert result.host_source == "github_initial_pr_head"
    assert result.expectation_fulfilled == "PASS"
    packet = result_payload(result)["provenance"]["initial_pr"]
    assert packet["initial_sha"] == protocol[1].expectation
    assert packet["artifact_id"] == 23
    assert "candidate_timestamp" not in packet
    html = render_check_html(result, repository="fixture/local", result_href="result.json").decode()
    assert "Original PR #11" in html
    assert "Original GitHub PR head" in html
    assert 'href="https://github.com/fixture/local/actions/runs/19/attempts/1"' in html
    assert 'href="https://github.com/fixture/local/actions/runs/19/artifacts/23"' in html
    assert "Every candidate submission in this PR follows its initial expectation head." in html


def test_causal_check_rejects_a_collector_outside_the_accepted_baseline(protocol) -> None:
    with pytest.raises(OrderingError):
        check(protocol, replace(protocol[2], collector_sha="a" * 40))


@pytest.mark.parametrize("change", ["missing-proof", "wrong-source"])
def test_result_schema_keeps_the_causal_source_bound_to_its_provenance(
    protocol, validator, change
) -> None:
    payload = result_payload(check(protocol, protocol[2]))
    validator.validate(payload)
    if change == "missing-proof":
        del payload["provenance"]["initial_pr"]
    else:
        payload["host_source"] = "supplied_records"
    assert not validator.is_valid(payload)
