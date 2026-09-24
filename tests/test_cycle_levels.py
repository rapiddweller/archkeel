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
from archkeel.check.validation import run_validate
from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.model import NoComponentCyclesRule, Observation, Record
from archkeel.ir.trace import trace_valid_violations
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


def _baselined_cycle(tmp_path: Path) -> tuple[Path, Path, str]:
    """The shop sample with one known model cycle, its baseline committed beside it."""
    files = {"architecture-contract.json": contract_with_rule(_MODULE_RULE), **_ALPHA_BETA}
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
