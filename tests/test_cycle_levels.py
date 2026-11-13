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

from archkeel.check.evaluation.topology import cycle_sections
from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.baseline import (
    KnownViolation,
    ViolationFingerprint,
    compare_violations,
    violation_drift_counts,
)
from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.facts_codec import RawRecord, classified
from archkeel.ir.model import EvidenceClass, NoComponentCyclesRule, Observation, Record
from archkeel.ir.widening import baseline_widenings
from fixtures.demo_catalog_dependencies import MODEL_MODULE_CYCLE, module_cycle_rule
from fixtures.demo_catalog_support import contract_with_rule

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

_GAMMA_DELTA = {
    "shop/model/gamma.py": "from shop.model import delta\nVALUE = delta.VALUE\n",
    "shop/model/delta.py": "from shop.model import gamma\nVALUE = 1\n",
}


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=root, stderr=subprocess.PIPE, text=True
    ).strip()


def _baselined_cycle(
    tmp_path: Path, cycle: dict[str, str] = MODEL_MODULE_CYCLE
) -> tuple[Path, Path, str]:
    """The shop sample with one known model cycle, its baseline committed beside it."""
    rule = module_cycle_rule(components=["model"])
    files = {"architecture-contract.json": contract_with_rule(rule), **cycle}
    root = _prepare_repo(tmp_path, files)
    baseline = root / "known-violations.json"
    result, written = run_validate(
        root, SHOP_CONFIG, observe, baseline=baseline, write_baseline=True
    )
    assert result.exit_code == 0, (result.diagnostics, result.failures)
    baseline.write_bytes(dict(written.entries)[str(baseline)])
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline the known cycle")
    return root, baseline, _git(root, "rev-parse", "HEAD")


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
