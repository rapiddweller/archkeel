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
    canonical_fingerprint,
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
from archkeel.ir.widening import baseline_widenings
from fixtures.demo_catalog_dependencies import REPOSITORY_WITH_MONEY_IMPORT

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
# AD-106: the refused run's last failure; no line of that run advises --write-baseline again.
REFUSED = (
    "--write-baseline refused: writing would accept the new or increased debt above; fix the "
    "code, or add --accept-new once an architect has decided to accept it"
)


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
    assert result.failures == (
        f"new violation: {GETATTR_RULE} | shop.model.probe_two.read "
        "(1 observed, 0 in the baseline)",
        REFUSED,
    )


def test_a_refused_write_says_why_and_how_to_proceed_without_advising_itself(
    tmp_path: Path,
) -> None:
    """Issue #152: `--write-baseline` printed "rewrite the baseline with --write-baseline" for
    the resolved entry of the very run it then refused because of the new one."""
    root = _repo(tmp_path, "refused-advice", {"shop/model/probe_two.py": SECOND_PROBE})
    known = (KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 1),)
    baseline = _baseline_file(root, known)

    plain, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)
    refused, files = run_validate(
        root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True
    )

    assert plain.failures[0].endswith("; rewrite the baseline with --write-baseline")
    assert (refused.exit_code, refused.artifact, files) == (1, None, {})
    assert refused.failures == (
        f"resolved violation: {GETATTR_RULE} | shop.model.probe.read "
        "(0 observed, 1 in the baseline)",
        f"new violation: {GETATTR_RULE} | shop.model.probe_two.read "
        "(1 observed, 0 in the baseline)",
        REFUSED,
    )


def test_a_refusal_stays_the_last_failure_beside_a_widening(tmp_path: Path) -> None:
    """AD-106: under --against the refused write also widens the committed baseline; the
    refusal still closes the list, so the way on is the last line read."""
    known = (KnownViolation(ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",)), 1),)
    root = _repo(
        tmp_path,
        "refused-against",
        {"shop/model/probe.py": PROBE, "known-violations.json": baseline_bytes(known).decode()},
    )
    (root / "shop/model/probe_two.py").write_text(SECOND_PROBE)

    result, files = run_validate(
        root,
        SHOP_CONFIG,
        observe,
        baseline=root / "known-violations.json",
        write_baseline=True,
        against="main",
    )

    assert (result.exit_code, files) == (1, {})
    assert result.failures == (
        f"new violation: {GETATTR_RULE} | shop.model.probe_two.read "
        "(1 observed, 0 in the baseline)",
        f"baseline entry widened: {GETATTR_RULE} | shop.model.probe_two.read (1 now, 0 before)",
        REFUSED,
    )


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


def test_a_baseline_entry_matches_its_violation_in_any_subject_order(tmp_path: Path) -> None:
    """Issue #152: a namespace renamed by text replace reorders an entry's subjects; the entry
    still names the same violation, and `--write-baseline` writes it back sorted."""
    root = _repo(tmp_path, "reordered", {"shop/store/repository.py": REPOSITORY_WITH_MONEY_IMPORT})
    baseline = root / "known-violations.json"
    _, files = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)
    written = json.loads(files[str(baseline)])
    subjects = ["shop.model.entities.Money", "shop.store.repository"]
    assert written["violations"][0]["subjects"] == subjects
    written["violations"][0]["subjects"].reverse()
    baseline.write_text(json.dumps(written))

    result, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)
    rewritten, files = run_validate(
        root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True
    )

    assert (result.exit_code, result.failures) == (0, ())
    assert (result.baseline_new, result.baseline_resolved) == (0, 0)
    assert (rewritten.exit_code, rewritten.failures) == (0, ())
    assert json.loads(files[str(baseline)])["violations"][0]["subjects"] == subjects


def test_a_fingerprint_is_the_same_in_any_list_order() -> None:
    """Sorted, not a set: a repeated subject still counts, so no two lists collapse into one."""
    parsed = parse_baseline(
        {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "budgets": {},
            "violations": [{"rules": ["B", "A"], "subjects": ["z", "a", "z"], "count": 1}],
        }
    )

    assert parsed[0].fingerprint == ViolationFingerprint(("A", "B"), ("a", "z", "z"))
    assert canonical_fingerprint(["A"], ["b", "a"]) == canonical_fingerprint(["A"], ["a", "b"])
    assert canonical_fingerprint(["A"], ["z", "a", "z"]) != canonical_fingerprint(["A"], ["a", "z"])


def test_two_entries_differing_only_in_subject_order_are_named_not_summed(
    tmp_path: Path,
) -> None:
    """One violation stated twice is an ambiguous file, exit 2 as `baseline.invalid`, never a
    count of two that could hide a second occurrence. --write-baseline reads the file first and
    stops the same way, so the remedy asks for a correction instead of advising it."""
    root = _repo(tmp_path, "repeated", {"shop/model/probe.py": PROBE})
    baseline = root / "known-violations.json"
    entry = {"rules": [GETATTR_RULE], "count": 1}
    baseline.write_text(
        json.dumps(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "budgets": {},
                "violations": [
                    {**entry, "subjects": ["a", "b"]},
                    {**entry, "subjects": ["b", "a"]},
                ],
            }
        )
    )

    plain, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)
    writing, files = run_validate(
        root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True
    )

    assert files == {}
    for result in (plain, writing):
        assert result.exit_code == 2
        ((code, claim, remedy),) = [
            (item.code, item.unknown_claim, item.remedy) for item in result.diagnostics
        ]
        assert code == "baseline.invalid"
        assert claim == (
            "The validation baseline cannot be read: baseline.violations[1] repeats "
            f"baseline.violations[0], {GETATTR_RULE} | a b (subjects match in any order); "
            "give it one count instead"
        )
        assert "--write-baseline" not in remedy


def test_order_free_identity_keeps_the_other_direction_visible() -> None:
    """Roles carry direction, so reading subjects in any order hides no violation: a reversed
    entry for `a -> b` does not absorb `b -> a`, and a role change still widens under --against.
    """
    known = parse_baseline(
        {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "budgets": {},
            "violations": [
                {
                    "rules": ["PEERS"],
                    "subjects": ["b", "a"],
                    "count": 1,
                    "roles": [{"source": "a", "target": "b"}],
                }
            ],
        }
    )
    fingerprint = ViolationFingerprint(("PEERS",), ("a", "b"))
    both_ways = (KnownViolation(fingerprint, 2, (("a", "b"), ("b", "a"))),)
    same = (KnownViolation(fingerprint, 1, (("a", "b"),)),)
    turned = (KnownViolation(fingerprint, 1, (("b", "a"),)),)

    assert compare_violations(known, both_ways, cycle_rules=frozenset()) == (
        "new violation: PEERS | a b (2 observed, 1 in the baseline)",
    )
    assert compare_violations(known, same, cycle_rules=frozenset()) == ()
    assert baseline_widenings(known, same, cycle_rules=frozenset()) == ()
    assert baseline_widenings(known, turned, cycle_rules=frozenset()) == (
        "baseline entry roles changed: PEERS | a b (a -> b before; b -> a now)",
    )


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
    # A missing file is what --write-baseline creates, so here it is the way on.
    assert "--write-baseline" in result.diagnostics[0].remedy


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


def test_baseline_rejects_metadata_outside_its_semantic_fields() -> None:
    with pytest.raises(ValueError, match="fields mismatch"):
        parse_baseline(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "violations": [
                    {
                        "rules": ["A"],
                        "subjects": ["b"],
                        "count": 1,
                        "note": "not semantic evidence",
                    }
                ],
            }
        )


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

    assert compare_violations(violations, violations, cycle_rules=frozenset()) == ()


def test_violation_drift_counts_are_deterministic() -> None:
    first = KnownViolation(ViolationFingerprint(("RULE-B",), ("second",)), 1)
    second = KnownViolation(ViolationFingerprint(("RULE-A",), ("first",)), 2)

    assert violation_drift_counts((first, second), (second,), cycle_rules=frozenset()) == (0, 1)


def test_violation_drift_counts_count_fingerprints_not_occurrences() -> None:
    fingerprint = ViolationFingerprint(("RULE-A",), ("first",))
    one = (KnownViolation(fingerprint, 1),)
    four = (KnownViolation(fingerprint, 4),)

    assert violation_drift_counts(one, four, cycle_rules=frozenset()) == (1, 0)
    assert violation_drift_counts(four, one, cycle_rules=frozenset()) == (0, 1)


def test_old_baseline_without_roles_remains_readable() -> None:
    fingerprint = ViolationFingerprint(("BOUNDARY",), ("shop.api", "shop.api.load"))

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
        ViolationFingerprint(("BOUNDARY",), ("shop.api", "shop.api.load")),
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
