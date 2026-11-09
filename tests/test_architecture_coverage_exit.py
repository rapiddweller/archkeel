# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The production exit code and the numeric receipt read the owner of coverage (#880, AD-322).

Each state runs through the production function. The old spelling is the oracle only. A PASS
status with recorded failures is incomplete everywhere: it gives exit code 2 and no complete
numeric receipt.
"""

import json
import random
from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_collection_boundary_regressions import _facts

import archkeel.check.observation as observation_module
from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.check.observation import assemble_observation
from archkeel.ir.coverage import observation_complete
from archkeel.ir.model import Verdict


def _old_exit_code(status: str) -> int:
    """The spelling before this change. It is the oracle only."""
    return 0 if status == "PASS" else 2


def _old_physically_complete(status: str, failures: int) -> bool:
    """The raw-dict spelling of `physically_complete` on the status. It is the oracle only."""
    return status == "PASS" and not failures


def _failure_json() -> dict[str, object]:
    return {
        "id": "FAILURE",
        "evidence_class": "UNKNOWN",
        "area": "analysis_coverage",
        "kind": "source_read_failure",
        "title": "one file was not read",
        "subjects": [],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {},
    }


def _force_coverage(monkeypatch: pytest.MonkeyPatch, status: str | None, failures: int) -> None:
    """Make the scan report this coverage. `None` removes the status."""

    def forced(*args, **kwargs):
        scan = evaluate_source(*args, **kwargs)
        if status is None:
            del scan.coverage["status"]
        else:
            scan.coverage["status"] = status
        scan.coverage["failures"] = [_failure_json() for _ in range(failures)]
        return scan

    monkeypatch.setattr(observation_module, "evaluate_source", forced)


def _assemble(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str | None, failures: int):
    _force_coverage(monkeypatch, status, failures)
    contract = tmp_path / "contract.json"
    contract.write_text('{"schema_version":"2.1.0","components":[],"rules":[]}')
    return assemble_observation(
        _facts(tmp_path),
        contract_root=tmp_path,
        contract_path=contract,
        roots=("src",),
        namespace="sample",
    )


def _numeric_receipt_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str, failures: int
) -> bool | None:
    """Run the numeric-operand rule and read `assessment_complete` from its receipt."""
    _force_coverage(monkeypatch, status, failures)
    contract = {
        "schema_version": "3.8.0",
        "components": [_component("core"), _component("cli")],
        "rules": [
            {
                "id": "RULE",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
                **_NUMERIC_RULE,
            }
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text("def choose(job_nonce):\n    return job_nonce % 16\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    receipt = next(
        item
        for item in result.observation.records("scope_observations") or ()
        if item.data.get("operation_binding")
    )
    return receipt.data.get("assessment_complete")  # type: ignore[return-value]


_NUMERIC_RULE = {
    "kind": "bounded_numeric_operand",
    "source": "sample.core",
    "form": "both",
    "terminal_suffix": "nonce",
    "minimum_value": 4_294_967_296,
}
# Every distinct state: the outcome depends on the status and on whether a failure is recorded.
_STATUS_VALUES = [verdict.value for verdict in Verdict]
_STATE_CASES = [(status, count) for status in _STATUS_VALUES for count in (0, 1, 2)]


@pytest.fixture(scope="module")
def exit_codes(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, int], tuple[int, bool]]:
    """Production exit code and `observation_complete` of each state, run once per state."""
    results: dict[tuple[str, int], tuple[int, bool]] = {}
    for status, count in _STATE_CASES:
        with pytest.MonkeyPatch.context() as patch:
            model, code = _assemble(tmp_path_factory.mktemp("state"), patch, status, count)
        results[(status, count)] = (code, observation_complete(model.coverage))
    return results


@pytest.mark.parametrize(("status", "count"), _STATE_CASES)
def test_the_exit_code_reads_the_status_and_the_failures(
    status: str, count: int, exit_codes: dict[tuple[str, int], tuple[int, bool]]
) -> None:
    code, complete = exit_codes[(status, count)]
    assert code == (0 if status == "PASS" and not count else 2)
    assert (code == 0) is complete


def test_only_a_pass_with_failures_changes_and_it_gets_more_cautious(
    exit_codes: dict[tuple[str, int], tuple[int, bool]],
) -> None:
    """2,000 generated scans, each run through the production exit code. The old spelling is
    the oracle: the codes agree, except a PASS with failures, which is now 2."""
    generator = random.Random(880)
    differences = 0
    for _ in range(2000):
        status, count = generator.choice(_STATE_CASES)
        code, _ = exit_codes[(status, count)]
        old = _old_exit_code(status)
        assert code >= old
        if code != old:
            differences += 1
            assert status == "PASS" and count
    assert differences > 0


@pytest.mark.parametrize(("status", "count"), _STATE_CASES)
def test_the_numeric_receipt_is_complete_as_the_owner_says(
    status: str, count: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`physically_complete` reads the raw dict. The production receipt equals the old spelling
    and the owner for every state."""
    complete = _numeric_receipt_complete(tmp_path, monkeypatch, status, count)
    assert complete is _old_physically_complete(status, count)


def test_a_missing_coverage_status_stays_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises((KeyError, ValueError)):
        _assemble(tmp_path, monkeypatch, None, 0)
