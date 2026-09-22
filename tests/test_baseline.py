# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-52: position-independent violation fingerprints and the known-violation baseline."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG as SHOP_CONFIG
from test_architecture_demo import _prepare_repo
from test_codec import raw_observation

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.ir.baseline import (
    BASELINE_SCHEMA_VERSION,
    KnownViolation,
    ViolationFingerprint,
    compare_violations,
    observed_violations,
    violation_drift_counts,
)
from archkeel.ir.codec import (
    baseline_bytes,
    decode_canonical_model,
    decode_json,
    parse_baseline,
    parse_observation,
)
from archkeel.ir.model import Observation

HEADER = (
    "# Archkeel\n# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.\n# SPDX-License-Identifier: MIT\n"
)
# One getattr in one function: the smallest overlay whose only finding is rule.violated.
PROBE = HEADER + (
    '"""Getattr probe for the baseline tests."""\n\n'
    "from __future__ import annotations\n\n\n"
    "class _Box:\n"
    "    value = 1\n\n\n"
    "def read() -> object:\n"
    '    return getattr(_Box(), "value")\n'
)
# The same violation with an unrelated line inserted above it: what moved every VIO- id.
MOVED_PROBE = PROBE.replace(
    "from __future__ import annotations\n",
    "from __future__ import annotations\n\n# An unrelated comment above the violation.\n",
)
TWICE_PROBE = PROBE.replace(
    '    return getattr(_Box(), "value")\n',
    '    first = getattr(_Box(), "value")\n    return first, getattr(_Box(), "value")\n',
)
SECOND_PROBE = PROBE.replace("Getattr probe", "Second getattr probe")
GETATTR_RULE = "CONSTRUCT-NO-DYNAMIC"


def _observe(root: Path) -> Observation:
    _, architecture = run_report(root, config=SHOP_CONFIG, analyzer=observe)
    assert architecture is not None
    return parse_observation(decode_canonical_model(json.loads(architecture)))


def _repo(tmp_path: Path, name: str, files: dict[str, str]) -> Path:
    return _prepare_repo(tmp_path / name, dict(files))


def _baseline_file(root: Path, violations: tuple[KnownViolation, ...]) -> Path:
    path = root / "known-violations.json"
    path.write_bytes(baseline_bytes(violations))
    return path


def test_a_moved_violation_keeps_its_fingerprint(tmp_path: Path) -> None:
    """The finding this issue was filed about: an edit above the line renamed the violation."""
    before = _observe(_repo(tmp_path, "before", {"shop/model/probe.py": PROBE}))
    after = _observe(_repo(tmp_path, "after", {"shop/model/probe.py": MOVED_PROBE}))

    assert observed_violations(before) == observed_violations(after)
    assert observed_violations(before) == (
        KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 1),
    )
    moved = [record.id for record in before.records("violations") or ()] != [
        record.id for record in after.records("violations") or ()
    ]
    assert moved, "VIO- ids are expected to move; the fingerprint is what must not"


def test_two_violations_in_one_function_share_a_fingerprint_and_are_counted(
    tmp_path: Path,
) -> None:
    observation = _observe(_repo(tmp_path, "twice", {"shop/model/probe.py": TWICE_PROBE}))

    assert observed_violations(observation) == (
        KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 2),
    )


def test_a_baselined_violation_passes_while_validate_alone_still_fails(tmp_path: Path) -> None:
    """Exit 0 with the baseline, and the unchanged exit 2 without it, on one repository."""
    root = _repo(tmp_path, "known", {"shop/model/probe.py": PROBE})
    baseline = _baseline_file(root, observed_violations(_observe(root)))

    result, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)

    assert (result.exit_code, result.failures, files) == (0, (), {})
    assert result.declared_rules == "FAIL"
    bare, _ = run_validate(root, SHOP_CONFIG, observe)
    assert bare.exit_code == 2
    assert [item.code for item in bare.diagnostics] == ["rule.violated"]


def test_a_new_violation_of_the_same_rule_in_another_module_fails(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        "new",
        {"shop/model/probe.py": PROBE, "shop/model/probe_two.py": SECOND_PROBE},
    )
    known = (KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 1),)
    baseline = _baseline_file(root, known)

    result, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)

    assert result.exit_code == 1
    assert result.diagnostics == ()
    assert result.failures == (
        f"new violation: {GETATTR_RULE} | shop.model.probe_two.read "
        "(1 observed, 0 in the baseline)",
    )


def test_updating_an_existing_baseline_refuses_new_fingerprints_by_default(
    tmp_path: Path,
) -> None:
    root = _repo(
        tmp_path,
        "refuse-update",
        {"shop/model/probe.py": PROBE, "shop/model/probe_two.py": SECOND_PROBE},
    )
    known = (KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 1),)
    baseline = _baseline_file(root, known)
    before = baseline.read_bytes()

    result, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)

    assert (result.exit_code, result.baseline_new, result.baseline_resolved, files) == (
        1,
        1,
        0,
        {},
    )
    assert baseline.read_bytes() == before


def test_accept_new_explicitly_updates_an_existing_baseline(tmp_path: Path) -> None:
    root = _repo(
        tmp_path,
        "accept-update",
        {"shop/model/probe.py": PROBE, "shop/model/probe_two.py": SECOND_PROBE},
    )
    baseline = _baseline_file(
        root,
        (KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 1),),
    )

    result, files = run_validate(
        root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True, accept_new=True
    )

    assert (result.exit_code, result.baseline_new, result.baseline_resolved) == (0, 1, 0)
    assert parse_baseline(decode_json(files[str(baseline)])) == observed_violations(_observe(root))


def test_updating_an_existing_baseline_refuses_an_increased_count(tmp_path: Path) -> None:
    root = _repo(tmp_path, "refuse-increase", {"shop/model/probe.py": TWICE_PROBE})
    known = (KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 1),)
    baseline = _baseline_file(root, known)

    result, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)

    assert (result.exit_code, result.baseline_new, result.baseline_resolved, files) == (
        1,
        1,
        0,
        {},
    )


def test_updating_an_existing_baseline_allows_resolved_only_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path, "resolve-update", {"shop/model/probe.py": PROBE})
    baseline = _baseline_file(
        root,
        (
            KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 1),
            KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.gone.read",)), 2),
        ),
    )

    result, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)

    assert (result.exit_code, result.baseline_new, result.baseline_resolved) == (0, 0, 1)
    assert parse_baseline(decode_json(files[str(baseline)])) == observed_violations(_observe(root))


def test_a_resolved_baseline_entry_is_reported(tmp_path: Path) -> None:
    root = _repo(tmp_path, "resolved", {"shop/model/probe.py": PROBE})
    known = (
        KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 1),
        KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.gone.read",)), 2),
    )
    baseline = _baseline_file(root, known)

    result, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)

    assert result.exit_code == 1
    assert result.failures == (
        f"resolved violation: {GETATTR_RULE} | shop.model.gone.read "
        "(0 observed, 2 in the baseline); rewrite the baseline with --write-baseline",
    )


def test_a_smaller_count_for_a_known_fingerprint_is_resolved_too(tmp_path: Path) -> None:
    """The budget only shrinks: two getattr calls baselined, one fixed, the file must follow."""
    root = _repo(tmp_path, "shrunk", {"shop/model/probe.py": PROBE})
    known = (KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 2),)
    baseline = _baseline_file(root, known)

    result, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)

    assert result.exit_code == 1
    assert "resolved violation" in result.failures[0]


def test_write_baseline_records_the_observed_violations(tmp_path: Path) -> None:
    root = _repo(tmp_path, "write", {"shop/model/probe.py": TWICE_PROBE})
    baseline = root / "known-violations.json"

    result, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)

    assert result.exit_code == 0
    assert result.artifact == str(baseline)
    written = parse_baseline(decode_json(files[str(baseline)]))
    assert written == (
        KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 2),
    )
    assert json.loads(files[str(baseline)])["schema_version"] == BASELINE_SCHEMA_VERSION


def test_a_written_baseline_passes_the_run_that_wrote_it(tmp_path: Path) -> None:
    root = _repo(tmp_path, "roundtrip", {"shop/model/probe.py": TWICE_PROBE})
    baseline = root / "known-violations.json"
    _, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)
    baseline.write_bytes(files[str(baseline)])

    result, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)

    assert (result.exit_code, result.failures) == (0, ())


def test_a_missing_baseline_file_is_exit_two_with_a_diagnostic(tmp_path: Path) -> None:
    root = _repo(tmp_path, "missing", {"shop/model/probe.py": PROBE})

    result, _ = run_validate(root, SHOP_CONFIG, observe, baseline=root / "does-not-exist.json")

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["baseline.invalid"]
    assert "does-not-exist.json" in result.diagnostics[0].subject


def test_an_unparsable_baseline_file_is_exit_two_with_a_diagnostic(tmp_path: Path) -> None:
    root = _repo(tmp_path, "broken", {"shop/model/probe.py": PROBE})
    baseline = root / "known-violations.json"
    baseline.write_text('{"schema_version": "1.0.0", "violations": [{"rules": "not-a-list"}]}')

    result, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)

    assert result.exit_code == 2
    assert [item.code for item in result.diagnostics] == ["baseline.invalid"]


def test_a_baseline_does_not_hide_any_other_diagnostic(tmp_path: Path) -> None:
    """Only rule.violated is answered by the baseline; a broken contract still exits 2."""
    root = _repo(tmp_path, "contract", {"shop/model/probe.py": PROBE})
    contract = json.loads((root / "architecture-contract.json").read_text())
    contract["rules"][0]["rationale"] = "TODO: decide this later."
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    baseline = _baseline_file(root, observed_violations(_observe(root)))

    result, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)

    assert result.exit_code == 2
    assert files == {}
    assert baseline.read_bytes() == baseline_bytes(observed_violations(_observe(root)))
    assert [item.code for item in result.diagnostics] == ["rationale.placeholder"]


@pytest.mark.parametrize(
    "payload",
    [
        {"violations": []},
        {"schema_version": "2.0.0", "violations": []},
        {"schema_version": BASELINE_SCHEMA_VERSION},
        {"schema_version": BASELINE_SCHEMA_VERSION, "violations": {}},
        {"schema_version": BASELINE_SCHEMA_VERSION, "violations": [{"rules": ["A"]}]},
        {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "violations": [{"rules": ["A"], "subjects": ["b"], "count": 0}],
        },
        {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "violations": [
                {"rules": ["A"], "subjects": ["b"], "count": 1},
                {"rules": ["A"], "subjects": ["b"], "count": 2},
            ],
        },
    ],
)
def test_a_malformed_baseline_document_is_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        parse_baseline(payload)


def test_a_baseline_document_round_trips() -> None:
    violations = (
        KnownViolation(ViolationFingerprint(("RULE-B",), ("second",)), 3),
        KnownViolation(ViolationFingerprint(("RULE-A",), ("first", "other")), 1),
    )

    written = parse_baseline(decode_json(baseline_bytes(violations)))

    assert written == tuple(sorted(violations, key=lambda item: item.fingerprint.rules))
    assert baseline_bytes(written) == baseline_bytes(violations)


def test_comparison_reports_nothing_when_the_baseline_states_the_observed_counts() -> None:
    violations = (KnownViolation(ViolationFingerprint(("RULE-A",), ("first",)), 2),)

    assert compare_violations(violations, violations) == ()


def test_violation_drift_counts_are_deterministic() -> None:
    first = KnownViolation(ViolationFingerprint(("RULE-B",), ("second",)), 1)
    second = KnownViolation(ViolationFingerprint(("RULE-A",), ("first",)), 2)

    assert violation_drift_counts((first, second), (second,)) == (0, 1)


def test_old_baseline_without_roles_remains_readable() -> None:
    fingerprint = ViolationFingerprint(("BOUNDARY",), ("shop.api.load", "shop.api"))

    assert parse_baseline(
        {
            "schema_version": "1.0.0",
            "violations": [
                {"rules": ["BOUNDARY"], "subjects": ["shop.api.load", "shop.api"], "count": 1}
            ],
        }
    ) == (KnownViolation(fingerprint, 1),)


def test_roles_are_sorted_and_do_not_change_fingerprint_identity() -> None:
    violation = KnownViolation(
        ViolationFingerprint(("BOUNDARY",), ("shop.api.load", "shop.api")),
        1,
        (("shop.z", "shop.a"), ("shop.a", "shop.z")),
    )

    payload = json.loads(baseline_bytes((violation,)))

    assert payload["schema_version"] == BASELINE_SCHEMA_VERSION
    assert payload["violations"][0]["roles"] == [
        {"source": "shop.a", "target": "shop.z"},
        {"source": "shop.z", "target": "shop.a"},
    ]
    assert parse_baseline(payload) == (
        KnownViolation(
            violation.fingerprint,
            violation.count,
            tuple(sorted(violation.roles)),
        ),
    )


def test_one_fingerprint_keeps_multiple_interface_boundary_directions() -> None:
    raw = raw_observation()
    raw["violations"] = [
        {
            "id": "VIO-one",
            "evidence_class": "VIOLATION",
            "area": "api_surface",
            "kind": "interface_boundary",
            "title": "one",
            "subjects": ["shop.api", "shop.api.load"],
            "evidence_ids": [],
            "rule_ids": ["BOUNDARY"],
            "fact_ids": [],
            "provenance": [],
            "data": {"source_module": "shop.api", "target_module": "shop.billing"},
        },
        {
            "id": "VIO-two",
            "evidence_class": "VIOLATION",
            "area": "api_surface",
            "kind": "interface_boundary",
            "title": "two",
            "subjects": ["shop.api", "shop.api.load"],
            "evidence_ids": [],
            "rule_ids": ["BOUNDARY"],
            "fact_ids": [],
            "provenance": [],
            "data": {"source_module": "shop.api", "target_module": "shop.orders"},
        },
    ]

    observed = observed_violations(parse_observation(raw))

    assert observed == (
        KnownViolation(
            ViolationFingerprint(("BOUNDARY",), ("shop.api", "shop.api.load")),
            2,
            (("shop.api", "shop.billing"), ("shop.api", "shop.orders")),
        ),
    )


def test_construct_rows_have_no_roles() -> None:
    raw = raw_observation()
    raw["violations"] = [
        {
            "id": "VIO-construct",
            "evidence_class": "VIOLATION",
            "area": "constructs",
            "kind": "forbidden_construct",
            "title": "construct",
            "subjects": ["shop.api.load"],
            "evidence_ids": [],
            "rule_ids": ["CONSTRUCT"],
            "fact_ids": [],
            "provenance": [],
            "data": {},
        }
    ]
    observed = observed_violations(parse_observation(raw))

    assert observed[0].roles == ()
    assert "roles" not in json.loads(baseline_bytes(observed))["violations"][0]
