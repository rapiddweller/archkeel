# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-98 (#129): `no_component_cycles` states the level and the components it holds acyclic."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_architecture_demo import CONFIG as SHOP_CONFIG
from test_architecture_demo import _prepare_repo

from archkeel.analyzer import observe
from archkeel.analyzer.embedded.dependencies import cycle_sections
from archkeel.analyzer.embedded.records import RawRecord, classified
from archkeel.check.validation import run_validate
from archkeel.ir.baseline import (
    KnownViolation,
    ViolationFingerprint,
    compare_violations,
    violation_drift_counts,
)
from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.model import EvidenceClass, NoComponentCyclesRule, Observation, Record
from archkeel.ir.trace import trace_valid_violations
from archkeel.ir.widening import baseline_widenings
from fixtures.demo_catalog_support import apply_overlay, contract_with_rule

_CORE_CYCLE = {
    "core/a.py": "from sample.core import b\n",
    "core/b.py": "from sample.core import a\n",
    "cli/main.py": "from sample.core import a\n",
}
_CLI_CYCLE = {
    "cli/x.py": "from sample.cli import y\n",
    "cli/y.py": "from sample.cli import x\n",
}


def _component(label: str) -> dict[str, object]:
    return {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [f"sample.{label}"],
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
    }


def _observe(
    tmp_path: Path,
    sources: dict[str, str],
    *,
    labels: tuple[str, ...] = ("core", "cli"),
    **rule: object,
) -> Observation:
    contract = {
        "schema_version": "2.1.0",
        "components": [_component(label) for label in labels],
        "rules": [
            {
                "id": "RULE",
                "kind": "no_component_cycles",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
                **rule,
            }
        ],
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    for name, text in sources.items():
        path = tmp_path / "sample" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    result = observe(
        tmp_path,
        roots=(".",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.diagnostics
    return result.observation


def _violations(observation: Observation) -> list[tuple[str, tuple[str, ...]]]:
    return [(item.kind, item.subjects) for item in observation.records("violations") or ()]


def _module_sccs(observation: Observation) -> list[tuple[str, ...]]:
    return [
        item.subjects for item in observation.records("cycles") or () if item.kind == "module_scc"
    ]


def _locations(observation: Observation, violation: Record) -> list[str]:
    evidence = {item.id: item for item in observation.evidence}
    return sorted(f"{evidence[key].file}:{evidence[key].line}" for key in violation.evidence_ids)


def test_the_component_rule_passes_while_a_module_cycle_exists(tmp_path: Path) -> None:
    """The issue's hidden risk: the declared level is acyclic, the module level is not."""
    observation = _observe(tmp_path, _CORE_CYCLE)

    assert _violations(observation) == []
    assert _module_sccs(observation) == [("sample.core.a", "sample.core.b")]


def test_the_module_level_names_members_and_the_imports_that_close_the_cycle(
    tmp_path: Path,
) -> None:
    observation = _observe(tmp_path, _CORE_CYCLE, level="module")

    (violation,) = trace_valid_violations(observation)
    assert (violation.kind, violation.subjects, violation.rule_ids) == (
        "module_cycle",
        ("sample.core.a", "sample.core.b"),
        ("RULE",),
    )
    assert violation.title == "Module cycle: sample.core.a ↔ sample.core.b"
    assert violation.data.get("members") == ("sample.core.a", "sample.core.b")
    assert violation.data.get("edges") == (
        ("sample.core.a", "sample.core.b"),
        ("sample.core.b", "sample.core.a"),
    )
    assert _locations(observation, violation) == ["sample/core/a.py:1", "sample/core/b.py:1"]
    # One graph: the rule judges exactly the SCC the report measures.
    assert [violation.subjects] == _module_sccs(observation)
    declaration = next(
        item for item in observation.records("declarations") or () if item.id == "RULE"
    )
    assert declaration.data.get("level") == "module"


@pytest.mark.parametrize(
    ("components", "expected"),
    [
        (None, [("sample.cli.x", "sample.cli.y"), ("sample.core.a", "sample.core.b")]),
        (["core"], [("sample.core.a", "sample.core.b")]),
        (["cli"], [("sample.cli.x", "sample.cli.y")]),
    ],
)
def test_module_level_scope_reports_the_cycles_that_touch_a_listed_component(
    tmp_path: Path, components: list[str] | None, expected: list[tuple[str, ...]]
) -> None:
    scope = {} if components is None else {"components": components}
    observation = _observe(tmp_path, {**_CORE_CYCLE, **_CLI_CYCLE}, level="module", **scope)

    assert sorted(subjects for _, subjects in _violations(observation)) == expected


def test_a_scoped_module_cycle_through_an_unowned_module_is_reported_whole(
    tmp_path: Path,
) -> None:
    """Scope selects which cycles matter; it never cuts a cycle short at the scope's edge."""
    sources = {"core/a.py": "from sample import extra\n", "extra.py": "from sample.core import a\n"}
    observation = _observe(tmp_path, sources, level="module", components=["core"])

    assert _violations(observation) == [("module_cycle", ("sample.core.a", "sample.extra"))]


def test_component_level_scope_reports_the_cycles_that_touch_a_listed_component(
    tmp_path: Path,
) -> None:
    sources = {
        "core/a.py": "from sample.cli import main\n",
        "cli/main.py": "from sample.core import a\n",
        "api/a.py": "from sample.db import b\n",
        "db/b.py": "from sample.api import a\n",
    }
    labels = ("core", "cli", "api", "db")

    unscoped = _observe(tmp_path / "all", sources, labels=labels)
    scoped = _observe(tmp_path / "core", sources, labels=labels, components=["core"])

    assert sorted(_violations(unscoped)) == [
        ("no_component_cycles", ("api", "db")),
        ("no_component_cycles", ("cli", "core")),
    ]
    assert _violations(scoped) == [("no_component_cycles", ("cli", "core"))]


def test_the_default_rule_keeps_its_records_and_its_canonical_contract(tmp_path: Path) -> None:
    """No `level` and no `components` is exactly the rule every existing contract declares."""
    sources = {
        "core/a.py": "from sample.cli import main\n",
        "cli/main.py": "import sample.core.a\n",
    }
    observation = _observe(tmp_path, sources)

    (violation,) = observation.records("violations") or ()
    assert (violation.kind, violation.title, violation.data.entries) == (
        "no_component_cycles",
        "Component cycle: cli ↔ core",
        (("members", ("cli", "core")),),
    )
    declaration = next(
        item for item in observation.records("declarations") or () if item.id == "RULE"
    )
    assert (declaration.title, declaration.subjects) == ("Component dependencies form no cycle", ())
    raw = json.loads((tmp_path / "contract.json").read_bytes())
    assert json.loads(contract_bytes(parse_contract(raw)))["rules"] == raw["rules"]


def test_the_contract_names_the_level_and_declared_components() -> None:
    raw = json.loads(_contract_json(level="component"))
    explicit = parse_contract(raw)
    del raw["rules"][0]["level"]
    # The default level is the absent one, so its canonical bytes and amendment digest match.
    assert explicit == parse_contract(raw)
    assert contract_bytes(explicit) == contract_bytes(parse_contract(raw))

    rule = parse_contract(json.loads(_contract_json(level="module", components=["core"]))).rules[0]
    assert isinstance(rule, NoComponentCyclesRule)
    assert (rule.level, rule.components) == ("module", ("core",))

    with pytest.raises(ValueError, match="names no declared component"):
        parse_contract(json.loads(_contract_json(components=["core", "missing"])))
    with pytest.raises(ValueError, match="level must be component or module"):
        parse_contract(json.loads(_contract_json(level="package")))


def _contract_json(**rule: object) -> str:
    return json.dumps(
        {
            "schema_version": "2.1.0",
            "components": [_component("core")],
            "rules": [
                {
                    "id": "RULE",
                    "kind": "no_component_cycles",
                    "rationale": "Probe.",
                    "provenance": ["docs/architecture/sample.md"],
                    "decided_by": "architect",
                    **rule,
                }
            ],
        }
    )


# --- A package SCC says whether a module cycle backs it or it is only the roll-up (#129). ---


def _package_sccs(observation: Observation) -> list[tuple[tuple[str, ...], str, object]]:
    return [
        (item.subjects, item.title, item.data.get("backed_by"))
        for item in observation.records("cycles") or ()
        if item.kind == "package_scc"
    ]


def _metric(observation: Observation, kind: str) -> tuple[object, tuple[str, ...]]:
    (metric,) = (item for item in observation.records("metrics") or () if item.kind == kind)
    return metric.data.get("value"), metric.fact_ids


def test_a_package_cycle_no_module_cycle_crosses_is_roll_up_only(tmp_path: Path) -> None:
    """a.x -> b.y and b.z -> a.w close a package cycle; no module path closes it (#129)."""
    sources = {
        "a/x.py": "from sample.b import y\n",
        "a/w.py": "VALUE = 1\n",
        "b/y.py": "VALUE = 1\n",
        "b/z.py": "from sample.a import w\n",
    }
    observation = _observe(tmp_path, sources, labels=())

    assert _module_sccs(observation) == []
    ((members, title, backed_by),) = _package_sccs(observation)
    assert (members, title, backed_by) == (
        ("sample.a", "sample.b"),
        "Package cycle with 2 members, roll-up only: no module cycle crosses them",
        (),
    )
    package_cycle = next(
        item.id for item in observation.records("cycles") or () if item.kind == "package_scc"
    )
    assert _metric(observation, "rollup_only_package_cycles") == (1, (package_cycle,))


def test_a_module_cycle_across_two_packages_backs_the_package_cycle(tmp_path: Path) -> None:
    sources = {
        "a/x.py": "from sample.b import y\n",
        "b/y.py": "from sample.a import x\n",
        # A module cycle inside one package backs no package cycle.
        "a/p.py": "from sample.a import q\n",
        "a/q.py": "from sample.a import p\n",
    }
    observation = _observe(tmp_path, sources, labels=())

    crossing = next(
        item.id
        for item in observation.records("cycles") or ()
        if item.kind == "module_scc" and item.subjects == ("sample.a.x", "sample.b.y")
    )
    assert _package_sccs(observation) == [
        (("sample.a", "sample.b"), "Package cycle with 2 members", (crossing,))
    ]
    assert _metric(observation, "rollup_only_package_cycles") == (0, ())


def _edge(level: str, source: str, target: str) -> RawRecord:
    return classified(
        item_id=f"EDGE-{source}-{target}",
        evidence_class=EvidenceClass.FACT,
        area=f"{level}_topology",
        kind=f"{level}_dependency",
        title=f"{source} -> {target}",
        data={"level": level, "source": source, "target": target},
    )


def _module(name: str) -> RawRecord:
    package = ".".join(name.split(".")[:2])
    return classified(
        item_id=f"MOD-{name}",
        evidence_class=EvidenceClass.FACT,
        area="module_topology",
        kind="module",
        title=name,
        data={"qualified_name": name, "package": package},
    )


def test_the_one_cycle_builder_annotates_every_package_cycle() -> None:
    """A profile gets package SCCs only with `backed_by` (review of #144): the Dart profile
    built them with the level-generic builder and the report's metric then raised KeyError."""
    module_pairs = [("sample.a.x", "sample.b.y"), ("sample.b.z", "sample.a.w")]
    package_pairs = [("sample.a", "sample.b"), ("sample.b", "sample.a")]

    module_cycles, cycles = cycle_sections(
        modules=[
            _module(name) for name in ("sample.a.w", "sample.a.x", "sample.b.y", "sample.b.z")
        ],
        packages=["sample.a", "sample.b"],
        module_edges=[_edge("module", *pair) for pair in module_pairs],
        module_edge_pairs=module_pairs,
        package_edges=[_edge("package", *pair) for pair in package_pairs],
        package_edge_pairs=package_pairs,
    )

    assert module_cycles == []
    assert [(item["kind"], item["subjects"], item["data"]["backed_by"]) for item in cycles] == [
        ("package_scc", ["sample.a", "sample.b"], [])
    ]


# --- The existing baseline and --against ratchet a module-level cycle count (#129, item 5). ---

_MODULE_RULE = {
    "id": "MODEL-MODULES-ACYCLIC",
    "kind": "no_component_cycles",
    "level": "module",
    "components": ["model"],
    "rationale": "Model modules import in one direction so each can be read on its own.",
    "provenance": ["docs/architecture/shop.md"],
    "decided_by": "architect",
}
_ALPHA_BETA = {
    "shop/model/alpha.py": "from shop.model import beta\nVALUE = beta.VALUE\n",
    "shop/model/beta.py": "from shop.model import alpha\nVALUE = 1\n",
}
_GAMMA_DELTA = {
    "shop/model/gamma.py": "from shop.model import delta\nVALUE = delta.VALUE\n",
    "shop/model/delta.py": "from shop.model import gamma\nVALUE = 1\n",
}


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=root, stderr=subprocess.PIPE, text=True
    ).strip()


def _baselined_cycle(tmp_path: Path, cycle: dict[str, str] = _ALPHA_BETA) -> tuple[Path, Path, str]:
    """The shop sample with one known model cycle, its baseline committed beside it."""
    files = {"architecture-contract.json": contract_with_rule(_MODULE_RULE), **cycle}
    root = _prepare_repo(tmp_path, files)
    baseline = root / "known-violations.json"
    result, written = run_validate(
        root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True
    )
    assert result.exit_code == 0, (result.diagnostics, result.failures)
    baseline.write_bytes(written[str(baseline)])
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline the known cycle")
    return root, baseline, _git(root, "rev-parse", "HEAD")


def test_a_baselined_module_cycle_passes_and_a_new_one_fails(tmp_path: Path) -> None:
    root, baseline, _ = _baselined_cycle(tmp_path)

    known, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)
    apply_overlay(root, _GAMMA_DELTA)
    grown, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)

    assert (known.exit_code, known.failures) == (0, ())
    assert (grown.exit_code, grown.failures) == (
        1,
        (
            "new violation: MODEL-MODULES-ACYCLIC | shop.model.delta shop.model.gamma "
            "(1 observed, 0 in the baseline)",
        ),
    )


def test_against_lets_the_cycle_count_fall_but_not_rise(tmp_path: Path) -> None:
    root, baseline, base = _baselined_cycle(tmp_path)

    apply_overlay(root, _GAMMA_DELTA)
    _, accepted = run_validate(
        root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True, accept_new=True
    )
    baseline.write_bytes(accepted[str(baseline)])
    risen, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, against=base)

    apply_overlay(root, {"shop/model/gamma.py": None, "shop/model/delta.py": None})
    apply_overlay(root, {"shop/model/beta.py": "VALUE = 1\n"})
    _, resolved = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True)
    baseline.write_bytes(resolved[str(baseline)])
    fallen, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, against=base)

    assert risen.exit_code == 1
    assert risen.failures == (
        "baseline entry widened: MODEL-MODULES-ACYCLIC | shop.model.delta shop.model.gamma "
        "(1 now, 0 before)",
    )
    assert (fallen.exit_code, fallen.failures) == (0, ())


# --- A cycle that shrinks inside a baselined one is that cycle contracting, not new (#129). ---

_CYCLE_RULES = frozenset({"CYCLES"})


def _baselined(*cycles: str) -> tuple[KnownViolation, ...]:
    return tuple(
        KnownViolation(ViolationFingerprint(("CYCLES",), tuple(cycle)), 1) for cycle in cycles
    )


@pytest.mark.parametrize(
    ("before", "after", "new"),
    [
        (("abc",), ("ab",), ()),
        (("abcd",), ("ab", "cd"), ()),
        (("ab",), ("abc",), ("abc",)),
        (("abc",), ("ab", "cd"), ("cd",)),
        # A baseline that keeps the old cycle beside its "part" is padded, not contracted.
        (("abc",), ("abc", "ab"), ("ab",)),
    ],
)
def test_a_cycle_inside_a_baselined_cycle_is_not_new(
    before: tuple[str, ...], after: tuple[str, ...], new: tuple[str, ...]
) -> None:
    known, observed = _baselined(*before), _baselined(*after)
    names = [" ".join(cycle) for cycle in new]

    drift = compare_violations(known, observed, cycle_rules=_CYCLE_RULES)
    assert [line for line in drift if line.startswith("new violation")] == [
        f"new violation: CYCLES | {name} (1 observed, 0 in the baseline)" for name in names
    ]
    assert violation_drift_counts(known, observed, cycle_rules=_CYCLE_RULES)[0] == len(new)
    assert baseline_widenings(known, observed, cycle_rules=_CYCLE_RULES) == tuple(
        f"baseline entry widened: CYCLES | {name} (1 now, 0 before)" for name in names
    )


def test_a_subset_under_a_rule_that_is_no_cycle_rule_stays_new() -> None:
    known, observed = _baselined("abc"), _baselined("ab")

    assert violation_drift_counts(known, observed, cycle_rules=frozenset()) == (1, 1)
    assert baseline_widenings(known, observed, cycle_rules=frozenset()) == (
        "baseline entry widened: CYCLES | a b (1 now, 0 before)",
    )


_THREE_MODULE_CYCLE = {
    "shop/model/alpha.py": "from shop.model import beta\nVALUE = beta.VALUE\n",
    "shop/model/beta.py": "from shop.model import alpha, gamma\nVALUE = 1\n",
    "shop/model/gamma.py": "from shop.model import beta\nVALUE = beta.VALUE\n",
}


def test_breaking_part_of_a_baselined_cycle_is_written_without_accepting_new_debt(
    tmp_path: Path,
) -> None:
    root, baseline, base = _baselined_cycle(tmp_path, _THREE_MODULE_CYCLE)

    apply_overlay(root, {"shop/model/gamma.py": "VALUE = 1\n"})
    drifted, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline)
    written, files = run_validate(
        root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True
    )
    baseline.write_bytes(files[str(baseline)])
    against, _ = run_validate(root, SHOP_CONFIG, observe, baseline=baseline, against=base)

    # The file still states the old cycle, so it must be rewritten, but nothing in it is new.
    assert (drifted.exit_code, drifted.baseline_new, drifted.baseline_resolved) == (1, 0, 1)
    assert drifted.failures == (
        "contracted violation: MODEL-MODULES-ACYCLIC | shop.model.alpha shop.model.beta "
        "(1 observed, 0 in the baseline) inside a baselined cycle; rewrite the baseline with "
        "--write-baseline",
        "resolved violation: MODEL-MODULES-ACYCLIC | shop.model.alpha shop.model.beta "
        "shop.model.gamma (0 observed, 1 in the baseline); rewrite the baseline with "
        "--write-baseline",
    )
    assert (written.exit_code, written.failures) == (0, ())
    assert (against.exit_code, against.failures) == (0, ())
