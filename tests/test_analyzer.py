# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import ast
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from test_delta import _model, _record

from archkeel.analyzer import observe
from archkeel.analyzer.embedded.calls import collect_calls
from archkeel.analyzer.embedded.constructs import collect_constructs
from archkeel.analyzer.embedded.imports import collect_imports
from archkeel.analyzer.embedded.resolve import build_symbol_index
from archkeel.analyzer.embedded.source import ParsedModule
from archkeel.analyzer.embedded.symbols import collect_symbols
from archkeel.analyzer.embedded.typing_signals import collect_typing_signals
from archkeel.analyzer.embedded.violations import _construct_violations, requires_violations
from archkeel.check.validation import COMPONENT_GRAPH_MARKER, observation_diagnostics
from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.interfaces import component_owners
from archkeel.ir.model import (
    Coverage,
    Diagnostic,
    ForbiddenConstructKind,
    ForbiddenConstructRule,
    Observation,
    ObservationResult,
    text_value,
)
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
EMBEDDED = ROOT / "src/archkeel/analyzer/embedded"


def test_analyzer_digest_covers_every_embedded_module() -> None:
    # AD-1: the analyzer digest hashes top-level modules only.
    nested = [
        path.relative_to(EMBEDDED).as_posix()
        for path in EMBEDDED.rglob("*.py")
        if path.parent != EMBEDDED and "__pycache__" not in path.parts
    ]
    assert nested == []


def _prepare_source(tmp_path: Path) -> None:
    metadata = tmp_path / "pyproject.toml"
    if not metadata.exists():
        metadata.write_text('[project]\nrequires-python = ">=3.11"\n')
    contract = tmp_path / "contract.json"
    if not contract.exists():
        contract.write_text('{"schema_version":"2.1.0","components":[],"rules":[]}')


def _observe(source: Path):
    _prepare_source(source)
    return observe(
        source,
        roots=(".",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=source,
    )


@pytest.mark.parametrize("exit_code", [2, True])
def test_analyzer_failure_cannot_become_complete(tmp_path: Path, exit_code: object) -> None:
    response = subprocess.CompletedProcess(
        [], 0, json.dumps({"model": {}, "exit_code": exit_code}), ""
    )
    with patch("archkeel.analyzer.subprocess.run", return_value=response):
        result = _observe(tmp_path)
    assert result.exit_code == 2
    assert result.diagnostics[0].kind == "parse_error"


def test_source_symlink_escape_is_rejected_before_analyzer(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("secret = 1\n")
    (source / "linked.py").symlink_to(outside)
    with patch("archkeel.analyzer.subprocess.run") as analyzer:
        result = _observe(source)
        analyzer.assert_not_called()
    assert result.exit_code == 2
    assert result.diagnostics[0].subject == str(source / "linked.py")
    assert "Source path escapes" in result.diagnostics[0].unknown_claim


def test_contract_1_1_has_migration_diagnostic(tmp_path: Path) -> None:
    (tmp_path / "contract.json").write_text('{"schema_version":"1.1.0","components":[],"rules":[]}')
    with patch("archkeel.analyzer.subprocess.run") as analyzer:
        result = _observe(tmp_path)
        analyzer.assert_not_called()
    assert result.exit_code == 2
    assert result.diagnostics == (
        Diagnostic(
            "parse_error",
            "contract.json",
            "Contract schema 1.1.0 cannot be validated as 2.1.0.",
            "Migrate the contract using docs/rules.md#migrating-from-1-1-0.",
        ),
    )


def test_forbidden_construct_produces_a_violation_and_contract_pointer(tmp_path: Path) -> None:
    contract_path = ROOT / "tests/contracts/valid/forbidden-construct.json"
    (tmp_path / "contract.json").write_bytes(contract_path.read_bytes())
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text('value = eval("1 + 1")\n')
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = result.observation.records("violations") or ()
    assert [(item.kind, item.rule_ids) for item in violations] == [
        ("forbidden_construct", ("CONSTRUCT-NO-DYNAMIC",))
    ]
    contract = parse_contract(decode_json(contract_path.read_bytes()))
    documents = (("docs/architecture/sample.md", f"{COMPONENT_GRAPH_MARKER}\n```mermaid\n```"),)
    diagnostics = observation_diagnostics(contract, result.observation, documents)
    assert any(item.pointer == "/rules/0" for item in diagnostics)


def _component(
    label: str, *, public: list[str] | None = None, planned: list[str] | None = None
) -> dict[str, object]:
    component: dict[str, object] = {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [f"sample.{label}"],
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
    }
    if public is not None:
        component["public"] = public
    if planned is not None:
        component["planned"] = planned
    return component


def test_rule_projection_writes_decided_by(tmp_path: Path) -> None:
    """AD-16: each rule's decided_by reaches its declaration record, not just the contract."""
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("core")],
        "rules": [
            {
                "id": "RULE-ARCHITECT",
                "kind": "no_component_cycles",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
            {
                "id": "RULE-AGENT",
                "kind": "complete_assignment",
                "source": "sample",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "agent",
            },
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    result = _observe(tmp_path)
    assert result.observation is not None
    declared = {
        record.id: record.data.get("decided_by")
        for record in result.observation.records("declarations") or ()
    }
    assert declared["RULE-ARCHITECT"] == "architect"
    assert declared["RULE-AGENT"] == "agent"


def test_component_projection_writes_who_decided_each_edge_and_the_public_list(
    tmp_path: Path,
) -> None:
    """AD-50: an edge and an interface reach the records with their decider resolved.

    The entry's own `decided_by` wins over the component's, which covers the rest of its
    `requires` list and its `public` list; a component that names neither attributes nothing.
    """
    contract = {
        "schema_version": "2.1.0",
        "components": [
            _component("core", public=["sample.core"]) | {"decided_by": "architect"},
            _component("api", public=[]),
            _component("cli")
            | {
                "decided_by": "agent",
                "requires": [
                    {"component": "core", "rationale": "Probe.", "decided_by": "architect"},
                    {"component": "api", "rationale": "Probe."},
                ],
            },
        ],
        "rules": [],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    result = _observe(tmp_path)
    assert result.observation is not None
    records = {
        record.id: record
        for record in result.observation.records("declarations") or ()
        if record.kind == "component_responsibility"
    }
    assert records["COMP-CORE"].data.get("decided_by") == "architect"
    assert records["COMP-API"].data.get("decided_by") is None
    assert [
        (entry.get("component"), entry.get("decided_by"))
        for entry in records["COMP-CLI"].data.get("requires")
    ] == [("api", "agent"), ("core", "architect")]


def _inside_component(label: str, requires: list[str]) -> dict[str, object]:
    return {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [f"sample.core.{label}"],
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
        "requires": [{"component": name, "rationale": "Probe."} for name in requires],
    }


def _with_inside(tmp_path: Path, inside: str, *, inner_rules: list[object] | None = None) -> None:
    outer = {
        "schema_version": "2.1.0",
        "components": [_component("core") | {"inside": inside}],
        "rules": [],
    }
    (tmp_path / "contract.json").write_text(json.dumps(outer))
    (tmp_path / "inner.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _inside_component("a", ["b"]),
                    _inside_component("b", []),
                ],
                "rules": inner_rules or [],
            }
        )
    )


_INNER_REQUIRES_RULE = {
    "id": "REQUIRES-COMPLETE",
    "kind": "complete_requires",
    "rationale": "Probe.",
    "provenance": ["docs/architecture/sample.md"],
    "decided_by": "architect",
}


def test_an_inside_crossing_no_requires_entry_covers_becomes_a_violation(tmp_path: Path) -> None:
    """AD-34: the inside is evaluated by the same rule code, so its verdict travels in the
    records every other verdict travels in, and reaches both the view and the exit code."""
    _with_inside(tmp_path, "inner.json", inner_rules=[_INNER_REQUIRES_RULE])
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/core/__init__.py").write_text("")
    # b requires nothing, so its import of a is the crossing absence forbids (AD-32).
    (tmp_path / "sample/core/a.py").write_text("V = 1\n")
    (tmp_path / "sample/core/b.py").write_text("import sample.core.a\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = [
        record
        for record in result.observation.records("violations") or ()
        if record.kind == "complete_requires"
    ]
    # The rule is recorded under the component holding the inside, and the violation names it
    # there, so the chain trace_valid_violations walks resolves (AD-36).
    assert [item.rule_ids for item in violations] == [("core:REQUIRES-COMPLETE",)]
    assert violations[0].data.get("source_module") == "sample.core.b"
    assert violations[0].data.get("target_module") == "sample.core.a"
    declared = {record.id for record in result.observation.records("declarations") or ()}
    assert "core:REQUIRES-COMPLETE" in declared


def test_an_inside_without_its_rule_decides_nothing(tmp_path: Path) -> None:
    """Without the rule nothing changes: no repository inherits this work by upgrading (AD-32)."""
    _with_inside(tmp_path, "inner.json")
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/core/__init__.py").write_text("")
    (tmp_path / "sample/core/a.py").write_text("V = 1\n")
    (tmp_path / "sample/core/b.py").write_text("import sample.core.a\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert result.observation.records("violations") == ()


def test_a_declared_inside_becomes_a_level_of_its_own(tmp_path: Path) -> None:
    """AD-34: the inside reaches the observation under a kind no existing reader consumes."""
    _with_inside(tmp_path, "inner.json")
    result = _observe(tmp_path)
    assert result.observation is not None
    records = {
        record.id: record
        for record in result.observation.records("declarations") or ()
        if record.kind == "inside_component_responsibility"
    }
    assert sorted(records) == ["core:COMP-A", "core:COMP-B"]
    assert records["core:COMP-A"].data.get("parent_id") == "core"
    assert [entry.get("component") for entry in records["core:COMP-A"].data.get("requires")] == [
        "b"
    ]
    assert records["core:COMP-A"].subjects == ("sample.core.a",)
    # The landmine AD-34 names: a shared kind would let two levels claim one module, and
    # `owner_of` answers None wherever two components claim the same one.
    assert component_owners(result.observation) == (("core", ("sample.core",)),)


def test_an_inside_that_leaves_the_repository_is_not_recorded(tmp_path: Path) -> None:
    """A contract path is attacker-adjacent input, so the analyzer reads none that escapes."""
    _with_inside(tmp_path, "../inner.json")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert not [
        record
        for record in result.observation.records("declarations") or ()
        if record.kind == "inside_component_responsibility"
    ]


@pytest.mark.parametrize(
    ("rule", "sources"),
    [
        (
            {
                "kind": "external_dependency_scope",
                "dependency": "json",
                "allowed_sources": ["sample.cli"],
            },
            {"core.py": "import json\n", "cli.py": "import json\n"},
        ),
        (
            {"kind": "complete_assignment", "source": "sample"},
            {"core.py": "V = 1\n", "cli.py": "V = 1\n", "extra.py": "V = 1\n", "blank.py": "\n"},
        ),
        (
            {"kind": "no_component_cycles"},
            {"core.py": "import sample.cli\n", "cli.py": "import sample.core\n"},
        ),
        (
            {"kind": "forbidden_construct", "source": "sample", "constructs": ["assert"]},
            {"core.py": "assert True\n"},
        ),
        (
            {
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["broad_except"],
                "allowed_sources": ["sample.cli"],
            },
            {
                "core.py": "try:\n    pass\nexcept Exception:\n    pass\n",
                "cli.py": "try:\n    pass\nexcept Exception:\n    pass\n",
            },
        ),
        (
            {
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["setattr", "delattr", "vars", "dunder_dict"],
            },
            {"core.py": 'setattr(object(), "x", 1)\n'},
        ),
        (
            {
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["string_literal_compare"],
                "allowed_sources": ["sample.cli"],
            },
            {
                "core.py": 'mode = "a"\nray = mode == "ray"\n',
                "cli.py": 'mode = "a"\nray = mode == "ray"\n',
            },
        ),
    ],
)
def test_class_a_rule_produces_one_traceable_violation(
    tmp_path: Path, rule: dict[str, object], sources: dict[str, str]
) -> None:
    result = _observe_one_rule(tmp_path, rule, sources)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids) for item in violations] == [(rule["kind"], ("RULE",))]
    assert len(result.observation.records("violations") or ()) == 1


_BROAD_EXCEPT = "try:\n    pass\nexcept Exception:\n    pass\n"


@pytest.mark.parametrize(
    ("rule", "sources", "subjects"),
    [
        (
            {
                "kind": "external_dependency_scope",
                "dependency": "json",
                "exact_sources": ["sample"],
            },
            {"__init__.py": "import json\n", "core.py": "import json\n"},
            ("json", "sample.core"),
        ),
        (
            {
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["broad_except"],
                "allowed_sources": ["sample.cli"],
                "exact_sources": ["sample"],
            },
            {
                "__init__.py": _BROAD_EXCEPT
                + "\n\ndef load():\n"
                + "".join(f"    {line}\n" for line in _BROAD_EXCEPT.splitlines()),
                "cli.py": _BROAD_EXCEPT,
            },
            ("sample.load",),
        ),
        (
            {
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["string_literal_compare"],
                "allowed_sources": ["sample.cli"],
                "exact_sources": ["sample"],
            },
            {
                "__init__.py": 'mode = "a"\nray = mode == "ray"\n\n\n'
                'def load(mode):\n    return mode == "ray"\n',
                "cli.py": 'mode = "a"\nray = mode == "ray"\n',
            },
            ("sample.load",),
        ),
    ],
)
def test_exact_sources_scope_the_package_root_and_nothing_below_it(
    tmp_path: Path,
    rule: dict[str, object],
    sources: dict[str, str],
    subjects: tuple[str, ...],
) -> None:
    """AD-49: an `exact_sources` entry allows the name itself, never what lies below it.

    The package root `sample` is a prefix of every module and scope in the package, so as an
    `allowed_sources` entry it would allow everything; as an exact entry it allows
    `sample/__init__.py`'s own imports and module-level code, and `sample.core` and the
    function `sample.load` stay forbidden.
    """
    result = _observe_one_rule(tmp_path, rule, sources)
    assert result.diagnostics == ()
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.subjects, item.rule_ids) for item in violations] == [(subjects, ("RULE",))]


@pytest.mark.parametrize(
    ("constructs", "exemptions", "recorded"),
    [
        (
            ["broad_except"],
            {"allowed_sources": ["sample.core", "sample.cli"], "exact_sources": ["sample"]},
            {"allowed_sources": ("sample.cli", "sample.core"), "exact_sources": ("sample",)},
        ),
        (["broad_except"], {}, {"allowed_sources": ()}),
        (
            ["setattr", "delattr", "vars", "dunder_dict", "string_literal_compare"],
            {"allowed_sources": ["sample.cli"], "exact_sources": ["sample"]},
            {"allowed_sources": ("sample.cli",), "exact_sources": ("sample",)},
        ),
    ],
)
def test_forbidden_construct_declaration_records_every_exemption(
    tmp_path: Path,
    constructs: list[str],
    exemptions: dict[str, list[str]],
    recorded: dict[str, tuple[str, ...]],
) -> None:
    """AD-49: the report shows every exemption a construct rule grants, prefix and exact.

    `exact_sources` is recorded only when the contract writes it, the way
    `external_dependency_scope` records it.
    """
    rule = {"kind": "forbidden_construct", "source": "sample", "constructs": constructs}
    result = _observe_one_rule(tmp_path, rule | exemptions, {"core.py": "V = 1\n"})
    assert result.observation is not None
    declared = {
        record.id: record.data for record in result.observation.records("declarations") or ()
    }
    exemption_fields = {
        key: value
        for key, value in declared["RULE"].entries
        if key in {"allowed_sources", "exact_sources"}
    }
    assert exemption_fields == recorded
    assert dict(declared["RULE"].entries)["constructs"] == tuple(constructs)


def _observe_one_rule(
    tmp_path: Path, rule: dict[str, object], sources: dict[str, str]
) -> ObservationResult:
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("core"), _component("cli")],
        "rules": [
            {
                "id": "RULE",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
                **rule,
            }
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    for name, text in sources.items():
        (tmp_path / "sample" / name).write_text(text)
    return _observe(tmp_path)


def _multi_package_worker() -> dict[str, object]:
    return {
        "id": "COMP-WORKER",
        "label": "worker",
        "role": "component",
        "packages": ["sample.orchestrator", "sample.worker"],
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
    }


def test_forbidden_dependency_naming_one_package_enforces_the_whole_component(
    tmp_path: Path,
) -> None:
    """A rule whose source and target each exactly name a declared component package
    decides (ir.decisions) and so enforces the whole ordered pair, not only the two named
    packages: an import into the target component's other package must violate it too.
    """
    contract = {
        "schema_version": "2.1.0",
        "components": [_multi_package_worker(), _component("outbox")],
        "rules": [
            {
                "id": "DEP-OUTBOX-NO-WORKER",
                "kind": "forbidden_dependency",
                "source": "sample.outbox",
                "target": "sample.orchestrator",
                "include_type_checking": True,
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/orchestrator.py").write_text("\n")
    (tmp_path / "sample/worker.py").write_text("\n")
    # Crosses into "worker" through its second package, never the one the rule names.
    (tmp_path / "sample/outbox.py").write_text("import sample.worker\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids) for item in violations] == [
        ("forbidden_dependency", ("DEP-OUTBOX-NO-WORKER",))
    ]


def test_forbidden_dependency_scoped_to_a_submodule_matches_only_that_submodule(
    tmp_path: Path,
) -> None:
    """A target below a whole component package (not an exact package match) keeps
    matching only that submodule, even on a component that owns several packages.
    """
    contract = {
        "schema_version": "2.1.0",
        "components": [_multi_package_worker(), _component("outbox")],
        "rules": [
            {
                "id": "DEP-OUTBOX-NO-WORKER-IMPL",
                "kind": "forbidden_dependency",
                "source": "sample.outbox",
                "target": "sample.worker.impl",
                "include_type_checking": True,
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/orchestrator.py").write_text("\n")
    (tmp_path / "sample/worker").mkdir()
    (tmp_path / "sample/worker/__init__.py").write_text("\n")
    (tmp_path / "sample/worker/impl.py").write_text("\n")
    (tmp_path / "sample/outbox.py").write_text(
        "import sample.orchestrator\nimport sample.worker.impl\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids) for item in violations] == [
        ("forbidden_dependency", ("DEP-OUTBOX-NO-WORKER-IMPL",))
    ]


def test_forbidden_dependency_supersedes_interface_boundary_on_the_same_import(
    tmp_path: Path,
) -> None:
    """AD-18: an import already rejected by forbidden_dependency is reported once, as
    that violation; interface_boundary does not also report it.
    """
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("core", public=["sample.core:allowed"]), _component("cli")],
        "rules": [
            {
                "id": "DEP-CLI-NO-CORE",
                "kind": "forbidden_dependency",
                "source": "sample.cli",
                "target": "sample.core",
                "include_type_checking": True,
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
            {
                "id": "INTERFACE",
                "kind": "interface_boundary",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text("allowed = 1\nother = 2\n")
    # Breaks both rules: forbidden_dependency (cli -> core) and interface_boundary (other
    # is not declared public).
    (tmp_path / "sample/cli.py").write_text("from sample.core import other\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids) for item in violations] == [
        ("forbidden_dependency", ("DEP-CLI-NO-CORE",))
    ]


def test_interface_boundary_still_fires_on_an_allowed_pair_that_misses_the_interface(
    tmp_path: Path,
) -> None:
    """AD-18 only supersedes an import a forbidden_dependency rule rejects; an import on
    a pair the architect has allowed, and that misses the declared interface, still
    violates interface_boundary.
    """
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("core", public=["sample.core:allowed"]), _component("cli")],
        "rules": [
            {
                "id": "DEP-CLI-ALLOWS-CORE",
                "kind": "allowed_dependency",
                "source": "sample.cli",
                "target": "sample.core",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
            {
                "id": "INTERFACE",
                "kind": "interface_boundary",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text("allowed = 1\nother = 2\n")
    (tmp_path / "sample/cli.py").write_text("from sample.core import other\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids) for item in violations] == [
        ("interface_boundary", ("INTERFACE",))
    ]


def test_scoped_forbidden_dependency_supersedes_only_the_imports_it_rejects(
    tmp_path: Path,
) -> None:
    """A target_symbol-scoped forbidden_dependency rule supersedes interface_boundary
    only on the import it rejects; a sibling import it does not reject still violates
    interface_boundary.
    """
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("core", public=["sample.core:allowed"]), _component("cli")],
        "rules": [
            {
                "id": "DEP-CLI-NO-CORE-HIDDEN-HELPER",
                "kind": "forbidden_dependency",
                "source": "sample.cli",
                "target": "sample.core.impl",
                "target_symbol": "hidden_helper",
                "include_type_checking": True,
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
            {
                "id": "INTERFACE",
                "kind": "interface_boundary",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core").mkdir()
    (tmp_path / "sample/core/__init__.py").write_text("allowed = 1\nother = 2\n")
    (tmp_path / "sample/core/impl.py").write_text("hidden_helper = 3\n")
    (tmp_path / "sample/cli").mkdir()
    # Rejected by the scoped forbidden_dependency rule; superseded, no interface finding.
    (tmp_path / "sample/cli/a.py").write_text("from sample.core.impl import hidden_helper\n")
    # Not in scope for the forbidden rule (targets sample.core, not sample.core.impl); the
    # interface violation still fires.
    (tmp_path / "sample/cli/b.py").write_text("from sample.core import other\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert sorted((item.kind, item.rule_ids) for item in violations) == [
        ("forbidden_dependency", ("DEP-CLI-NO-CORE-HIDDEN-HELPER",)),
        ("interface_boundary", ("INTERFACE",)),
    ]


@pytest.mark.parametrize(
    ("core_public", "rule_overrides", "files", "expected_violations"),
    [
        (
            ["sample.core"],
            {},
            {
                "sample/core.py": "_hidden = 1\n",
                "sample/cli.py": "from sample.core import _hidden\n",
            },
            1,
        ),
        (
            ["sample.core:allowed"],
            {},
            {
                "sample/core.py": "allowed = 1\nother = 2\n",
                "sample/cli.py": "from sample.core import other\n",
            },
            1,
        ),
        (
            ["sample.core:allowed"],
            {},
            {
                "sample/core.py": "allowed = 1\n",
                "sample/cli.py": "import sample.core\n",
            },
            1,
        ),
        (
            ["sample.core.impl:Widget"],
            {},
            {
                "sample/core/__init__.py": "from .impl import Widget\n",
                "sample/core/impl.py": "class Widget:\n    pass\n",
                "sample/cli.py": "from sample.core import Widget\n",
            },
            0,
        ),
        (
            ["sample.core:allowed"],
            {"include_type_checking": False},
            {
                "sample/core.py": "allowed = 1\nother = 2\n",
                "sample/cli.py": (
                    "from typing import TYPE_CHECKING\n"
                    "if TYPE_CHECKING:\n"
                    "    from sample.core import other\n"
                ),
            },
            0,
        ),
        (
            ["sample.core"],
            {},
            {
                "sample/core.py": '__all__ = ["a"]\na = 1\nb = 2\n',
                "sample/cli.py": "from sample.core import b\n",
            },
            1,
        ),
        (
            ["sample.core.impl"],
            {},
            {
                "sample/core/__init__.py": "\n",
                "sample/core/impl.py": "class Widget:\n    pass\n",
                "sample/cli.py": "from sample.core import impl\n",
            },
            0,
        ),
        (
            ["sample.core:impl"],
            {},
            {
                "sample/core/__init__.py": "\n",
                "sample/core/impl.py": "class Widget:\n    pass\n",
                "sample/cli.py": "from sample.core import impl\n",
            },
            1,
        ),
    ],
)
def test_interface_boundary_rule_matches_the_declared_public_interface(
    tmp_path: Path,
    core_public: list[str],
    rule_overrides: dict[str, object],
    files: dict[str, str],
    expected_violations: int,
) -> None:
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("core", public=core_public), _component("cli")],
        "rules": [
            {
                "id": "INTERFACE",
                "kind": "interface_boundary",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
                **rule_overrides,
            }
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    for relative_path, text in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = [
        item
        for item in result.observation.records("violations") or ()
        if item.kind == "interface_boundary"
    ]
    assert len(violations) == expected_violations


@pytest.mark.parametrize("cause", ["missing_tool", "timeout", "parse_error"])
def test_execution_failure_has_structured_diagnostic(tmp_path: Path, cause: str) -> None:
    if cause == "missing_tool":
        error: Exception = OSError("missing Python executable")
    elif cause == "timeout":
        error = subprocess.TimeoutExpired("analyzer", 60)
    else:
        error = ValueError("unused")
    if cause in {"missing_tool", "timeout"}:
        with patch("archkeel.analyzer.subprocess.run", side_effect=error):
            result = _observe(tmp_path)
    else:
        with patch(
            "archkeel.analyzer.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "not JSON", ""),
        ):
            result = _observe(tmp_path)
    assert result.exit_code == 2
    assert result.observation is None
    assert result.coverage is None
    assert result.diagnostics[0].kind == cause
    assert all(isinstance(item, Diagnostic) for item in result.diagnostics)


@pytest.mark.parametrize("cause", ["scope_empty", "rule_without_subjects"])
def test_partial_observation_and_coverage_survive_exit_two(tmp_path: Path, cause: str) -> None:
    raw = _model(git_head="a" * 40)
    coverage = raw["coverage"]
    coverage["status"] = "FAIL"
    if cause == "scope_empty":
        coverage.update(files_discovered=0, files_read=0, files_parsed=0)
    else:
        failure = _record("unknown-rule", kind="rule-without-subjects", evidence_class="UNKNOWN")
        failure["rule_ids"] = ["rule-zero"]
        raw["unknowns"] = [failure]
        coverage.update(rules="FAIL", failures=[failure])
    response = subprocess.CompletedProcess([], 0, json.dumps({"model": raw, "exit_code": 2}), "")
    with patch("archkeel.analyzer.subprocess.run", return_value=response):
        result = _observe(tmp_path)
    assert result.exit_code == 2
    assert isinstance(result.observation, Observation)
    assert isinstance(result.coverage, Coverage)
    assert result.coverage is result.observation.coverage
    assert result.diagnostics[0].kind == cause
    if cause == "rule_without_subjects":
        assert result.diagnostics[0].subject == "rule-zero"
        assert result.observation.records("unknowns")[0].id == "unknown-rule"


def _parsed_module(
    source: str,
    module: str = "sample.mod",
    *,
    rel_path: str = "sample/mod.py",
    package: str = "sample",
) -> ParsedModule:
    return ParsedModule(
        path=Path(rel_path),
        rel_path=rel_path,
        module=module,
        package=package,
        source=source,
        source_bytes=source.encode(),
        lines=source.splitlines(),
        tree=ast.parse(source),
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("try:\n    pass\nexcept:\n    pass\n", [("broad_except", "sample.mod")]),
        (
            "try:\n    pass\nexcept (ValueError, Exception):\n    pass\n",
            [("broad_except", "sample.mod")],
        ),
        (
            "import builtins\ntry:\n    pass\nexcept builtins.Exception:\n    pass\n",
            [("broad_except", "sample.mod")],
        ),
        ("try:\n    pass\nexcept Exception:\n    raise\n", [("broad_except", "sample.mod")]),
        ("try:\n    pass\nexcept* Exception:\n    pass\n", [("broad_except", "sample.mod")]),
        (
            "class Widget:\n    def m(self):\n        try:\n            pass\n"
            "        except Exception:\n            pass\n",
            [("broad_except", "sample.mod.Widget.m")],
        ),
        ("try:\n    pass\nexcept ValueError:\n    pass\n", []),
        ("E = Exception\ntry:\n    pass\nexcept E:\n    pass\n", []),
    ],
)
def test_collect_constructs_detects_broad_except_and_documented_blind_spots(
    source: str, expected: list[tuple[str, str]]
) -> None:
    records = collect_constructs([_parsed_module(source)], {})
    assert sorted((item["kind"], item["data"]["owner"]) for item in records) == sorted(expected)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('setattr(box, "x", 1)\n', [("setattr_call", "sample.mod")]),
        ('delattr(box, "x")\n', [("delattr_call", "sample.mod")]),
        ("vars(box)\nvars()\n", [("vars_call", "sample.mod"), ("vars_call", "sample.mod")]),
        (
            'import builtins\nbuiltins.setattr(box, "x", 1)\n',
            [("setattr_call", "sample.mod")],
        ),
        (
            "class Widget:\n    def m(self):\n        return self.__dict__\n",
            [("dunder_dict", "sample.mod.Widget.m")],
        ),
        ('box.__dict__["x"] = 1\ndel box.__dict__["x"]\n', [("dunder_dict", "sample.mod")] * 2),
        ("box.__dict__.__dict__\n", [("dunder_dict", "sample.mod")]),
        ('box.setattr("x", 1)\nbox.vars()\n', []),
        ('f = setattr\nf(box, "x", 1)\n', []),
        ('object.__setattr__(box, "x", 1)\n', []),
    ],
)
def test_collect_constructs_detects_reflection_as_written(
    source: str, expected: list[tuple[str, str]]
) -> None:
    """AD-48: the write side of reflection is matched as written; aliases stay blind spots."""
    records = collect_constructs([_parsed_module(source)], {})
    assert sorted((item["kind"], item["data"]["owner"]) for item in records) == sorted(expected)
    assert len({item["id"] for item in records}) == len(records)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('if mode == "ray":\n    pass\n', [("sample.mod", "compare")]),
        ('if "ray" != mode:\n    pass\n', [("sample.mod", "compare")]),
        ('ok = a == "x" or b == "y"\n', [("sample.mod", "compare")] * 2),
        ('ok = low < mode == "ray"\n', [("sample.mod", "compare")]),
        ('ok = mode in ("a", "b")\n', [("sample.mod", "membership")]),
        ('ok = mode not in ["a"]\n', [("sample.mod", "membership")]),
        ('ok = mode in {"a", "b"}\n', [("sample.mod", "membership")]),
        (
            'def f(mode):\n    match mode:\n        case "a":\n            pass\n'
            '        case "b" | "c":\n            pass\n',
            [("sample.mod.f", "match")],
        ),
        (
            'match command:\n    case ["go", where]:\n        pass\n',
            [("sample.mod", "match")],
        ),
        ('if __name__ == "__main__":\n    pass\n', []),
        (
            'EMPTY = ""\n\ndef f(value: str) -> bool:\n    return value == EMPTY\n',
            [("sample.mod.f", "compare")],
        ),
        (
            "from typing import Final\n"
            'EMPTY: Final[str] = ""\n\n'
            "def f(value: str) -> bool:\n"
            "    return value == EMPTY\n",
            [("sample.mod.f", "compare")],
        ),
        (
            'EMPTY = ""\n\ndef f(value: str) -> bool:\n    return value in (EMPTY,)\n',
            [("sample.mod.f", "membership")],
        ),
        (
            "class Labels:\n"
            '    EMPTY: str = ""\n\n'
            "def f(value: str) -> bool:\n"
            "    return value == Labels.EMPTY\n",
            [("sample.mod.f", "compare")],
        ),
        (
            "class Labels:\n"
            '    EMPTY = ""\n\n'
            "    def f(self, value: str) -> bool:\n"
            "        return value == self.EMPTY\n",
            [],
        ),
        (
            "from enum import Enum\n\n"
            "class Labels(Enum):\n"
            '    EMPTY = ""\n\n'
            "def f(value: str) -> bool:\n"
            "    return value == Labels.EMPTY\n",
            [],
        ),
        (
            'EMPTY = ""\n'
            'EMPTY = "other"\n\n'
            "def f(value: str) -> bool:\n"
            "    return value == EMPTY\n",
            [],
        ),
        (
            "if enabled:\n"
            '    EMPTY = ""\n\n'
            "def f(value: str) -> bool:\n"
            "    return value == EMPTY\n",
            [],
        ),
        (
            "from other import EMPTY\n\ndef f(value: str) -> bool:\n    return value == EMPTY\n",
            [],
        ),
        (
            "EMPTY = read_value()\n\ndef f(value: str) -> bool:\n    return value == EMPTY\n",
            [],
        ),
        (
            "class Labels:\n"
            '    EMPTY = ""\n'
            '    EMPTY = "other"\n\n'
            "def f(value: str) -> bool:\n"
            "    return value == Labels.EMPTY\n",
            [],
        ),
        (
            "class Labels:\n"
            '    EMPTY = ""\n\n'
            'Labels.EMPTY = "other"\n\n'
            "def f(value: str) -> bool:\n"
            "    return value == Labels.EMPTY\n",
            [],
        ),
        ("ok = mode == 5\n", []),
        ('ok = mode == f"{x}"\n', []),
        ('ok = mode == b"a"\n', []),
        ('ok = mode < "b"\n', []),
        ('ok = mode in ("a", 1)\n', []),
        ("ok = mode in ()\n", []),
        ('ok = mode in {"a": 1}\n', []),
        ("ok = mode in names\n", []),
        ('ok = "a" in text\n', []),
        ('ok = mode.startswith("a")\n', []),
        (
            "match point:\n    case Point():\n        pass\n"
            '    case {"kind": _}:\n        pass\n    case Color.RED:\n        pass\n',
            [],
        ),
    ],
)
def test_collect_constructs_detects_string_literal_compare_and_its_exclusions(
    source: str, expected: list[tuple[str, str]]
) -> None:
    """AD-48: one record per comparison or match statement, with the form it takes."""
    records = collect_constructs([_parsed_module(source)], {})
    found = [
        (item["data"]["owner"], item["data"]["form"])
        for item in records
        if item["kind"] == "string_literal_compare"
    ]
    assert sorted(found) == sorted(expected)
    assert len({item["id"] for item in records}) == len(records)


def _any_rule(source: str = "sample") -> ForbiddenConstructRule:
    return ForbiddenConstructRule(
        "R",
        "forbidden_construct",
        source,
        (ForbiddenConstructKind.ANY_ANNOTATION,),
        "because",
        (),
        "architect",
    )


@pytest.mark.parametrize(
    ("source", "expected_owner"),
    [
        # Module-level: before AD-62 the owner was the bare target name ("X"), which never
        # starts with "sample", so `in_scope` rejected it and the violation never fired.
        ("from typing import Any\nX: dict[str, Any] = {}\n", "sample.mod.X"),
        # Class-level: same bug, the bare attribute name ("x") was equally unscoped.
        (
            "from typing import Any\nclass Box:\n    x: dict[str, Any] = {}\n",
            "sample.mod.Box.x",
        ),
        # Function-local: ast.walk found the AnnAssign with no enclosing-function context at all.
        (
            "from typing import Any\ndef f() -> None:\n    x: dict[str, Any] = {}\n",
            "sample.mod.f.x",
        ),
        # Function parameter: already correct before the fix, and must stay that way.
        (
            "from typing import Any\ndef f(value: Any) -> None:\n    pass\n",
            "sample.mod.f:value",
        ),
    ],
)
def test_collect_typing_signals_scopes_annassign_owner_to_its_enclosing_scope(
    source: str, expected_owner: str
) -> None:
    """AD-62: an annotated variable's owner names the scope it is written in, exactly like a
    function's owner already did, so a source-scoped forbidden_construct rule can see it.

    Before the fix, `collect_typing_signals` gave a module- or class-level annotated variable
    the bare target name as its owner (`annotation_text(node.target) or module.module`), with
    no module or class prefix; `_construct_violations` scopes by `owner.split(":", 1)[0]` and
    `in_scope`, so a bare name under a package it never named as its prefix was silently
    dropped -- the rule fired on a parameter but never on a variable of the same annotation.
    """
    records = collect_typing_signals([_parsed_module(source)], [], [], [], {})
    any_records = [item for item in records if item["kind"] == "any_annotation"]
    assert [item["data"]["owner"] for item in any_records] == [expected_owner]
    violations = _construct_violations(any_records, [_any_rule()])
    assert len(violations) == 1


def test_collect_typing_signals_scopes_a_nested_function_to_its_enclosing_function() -> None:
    """A closure gets the same fix as a method or a variable: its owner carries the outer
    function's name, not just the module's, since both come from the one scope-tracking walk."""
    source = (
        "from typing import Any\ndef outer():\n    def inner(value: Any) -> None:\n        pass\n"
    )
    records = collect_typing_signals([_parsed_module(source)], [], [], [], {})
    any_records = [item for item in records if item["kind"] == "any_annotation"]
    assert [item["data"]["owner"] for item in any_records] == ["sample.mod.outer.inner:value"]


@pytest.mark.parametrize(
    ("source", "expression", "status", "targets", "reason"),
    [
        (
            'def f(items: list[str]) -> None:\n    "".join(items)\n',
            "''.join",
            "resolved",
            ["builtins.str.join"],
            "literal receiver of known type",
        ),
        (
            'def f() -> None:\n    diagnostics = []\n    diagnostics.append("x")\n',
            "diagnostics.append",
            "resolved",
            ["builtins.list.append"],
            "literal-bound receiver of known type",
        ),
        (
            'def f(items: list[str]) -> None:\n    items.append("x")\n',
            "items.append",
            "partially_resolved",
            ["builtins.list.append"],
            "annotated receiver of known type, unproven at runtime",
        ),
        (
            'def f() -> None:\n    items: list[str]\n    items.append("x")\n',
            "items.append",
            "partially_resolved",
            ["builtins.list.append"],
            "annotated receiver of known type, unproven at runtime",
        ),
        (
            "def make() -> list[str]:\n    return []\n\n\n"
            'def f() -> None:\n    make().append("x")\n',
            "make().append",
            "unresolved",
            [],
            "expression is dynamic",
        ),
        (
            "def f() -> None:\n    items = []\n    items.frobnicate()\n",
            "items.frobnicate",
            "unresolved",
            [],
            "dynamic attribute receiver",
        ),
        (
            "def make():\n    return object()\n\n\n"
            'def f() -> None:\n    items = []\n    items = make()\n    items.append("x")\n',
            "items.append",
            "unresolved",
            [],
            "dynamic attribute receiver",
        ),
        (
            "def f(items: list[str]) -> None:\n"
            '    for items in rows():\n        items.append("x")\n',
            "items.append",
            "unresolved",
            [],
            "dynamic attribute receiver",
        ),
    ],
)
def test_receiver_typed_calls_resolve_or_name_why_not(
    source: str, expression: str, status: str, targets: list[str], reason: str
) -> None:
    """AD-37: a receiver's static type resolves a stdlib method call, or names why not.

    Covers each resolution source in turn — a literal written at the call site, a local
    bound to a literal, an annotated parameter, an annotated local — plus a call-result
    receiver, which AD-37 leaves out of scope, a method the frozen table does not name, and
    a name rebound to something else (a plain reassignment, then a `for` target): every
    binding of a name must agree, so either rebinding voids it rather than keeping the first
    or the last answer.
    """
    index = build_symbol_index([])
    calls = collect_calls([_parsed_module(source)], index, {})
    match = next(item for item in calls if item["data"]["expression"] == expression)
    assert match["data"]["status"] == status
    assert match["data"]["targets"] == targets
    assert match["data"]["reason"] == reason


def test_every_source_failure_uses_runtime_mismatch_with_an_older_parser(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
    raw = _model(git_head="a" * 40)
    failures = [
        _record(str(index), kind=kind, evidence_class="UNKNOWN")
        for index, kind in enumerate(("SyntaxError", "IndentationError", "TabError"))
    ]
    raw["coverage"].update(status="FAIL", files_parsed=0, failures=failures)
    response = subprocess.CompletedProcess([], 0, json.dumps({"model": raw, "exit_code": 2}), "")
    with patch("archkeel.analyzer.subprocess.run", return_value=response):
        result = _observe(tmp_path)
    assert result.exit_code == 2
    assert result.observation.coverage.failures
    assert len(result.diagnostics) == len(failures)
    assert {item.kind for item in result.diagnostics} == {"runtime_mismatch"}


def test_context_reads_reflect_walk_order_and_nested_function_duplication(
    tmp_path: Path,
) -> None:
    # Pins two collect_contexts quirks so a refactor cannot silently change them:
    # (1) `bindings` is mutated while `ast.walk` runs, so a read whose Assign sits
    #     deeper in the tree than the read (here: the read is shallower, the
    #     writing Assign is nested two `if`s down) is visited first and, since
    #     the binding does not exist yet, is never recorded; and
    # (2) a nested function is walked twice -- once while its outer function is
    #     walked, once as its own top-level function -- so one source read
    #     produces two `context_read` records under two different scopes.
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/contexts.py").write_text(
        "from dataclasses import dataclass\n\n\n@dataclass\nclass FooContext:\n    value: int = 0\n"
    )
    (tmp_path / "sample/core.py").write_text(
        "from sample.contexts import FooContext\n\n\n"
        "def use() -> None:\n"
        "    print(ctx.value)\n"
        "    if True:\n"
        "        if True:\n"
        "            ctx = FooContext()\n\n\n"
        "def outer(ctx: FooContext) -> None:\n"
        "    def inner(ctx: FooContext) -> None:\n"
        "        return ctx.value\n\n"
        "    return inner(ctx)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    context_evidence = result.observation.records("context_evidence") or ()
    reads = sorted(
        (
            item.data.get("source"),
            item.data.get("field"),
            item.data.get("path"),
            item.data.get("access"),
        )
        for item in context_evidence
        if item.kind == "context_read" and item.data.get("context") == "sample.contexts.FooContext"
    )
    assert reads == [
        ("sample.core.inner", "value", "value", "read"),
        ("sample.core.outer", "value", "value", "read"),
    ]
    fooctx_evidence = [
        item
        for item in context_evidence
        if item.data.get("context") == "sample.contexts.FooContext"
    ]
    assert sorted((item.kind, item.data.get("source")) for item in fooctx_evidence) == [
        ("context_construction", "sample.core.use"),
        ("context_dependency", None),
        ("context_field", None),
        ("context_pass", "sample.core.outer"),
        ("context_read", "sample.core.inner"),
        ("context_read", "sample.core.outer"),
    ]


def test_sibling_isolation_reports_a_peer_import_but_not_a_shared_one(tmp_path: Path) -> None:
    """AD-25: peers of one set reach shared modules, never each other."""
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("core")],
        "rules": [
            {
                "id": "SIBLINGS",
                "kind": "sibling_isolation",
                "members": ["sample.core.first", "sample.core.second"],
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/core/__init__.py").write_text("")
    (tmp_path / "sample/core/shared.py").write_text("VALUE = 1\n")
    # Allowed: a peer reaches a shared module that is not a member.
    (tmp_path / "sample/core/first.py").write_text("from sample.core.shared import VALUE\n")
    # Violation: one peer imports the other.
    (tmp_path / "sample/core/second.py").write_text("from sample.core.first import VALUE\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids) for item in violations] == [
        ("sibling_isolation", ("SIBLINGS",))
    ]


def test_symbol_placement_reports_a_class_outside_its_allowed_module(tmp_path: Path) -> None:
    """AD-58: a class of a declared kind below source is defined only in an allowed module."""
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("model")],
        "rules": [
            {
                "id": "MODEL-TYPES-IN-ENTITIES",
                "kind": "symbol_placement",
                "source": "sample.model",
                "class_kinds": ["dataclass"],
                "exact_sources": ["sample.model.entities"],
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/model").mkdir(parents=True)
    (tmp_path / "sample/model/__init__.py").write_text("")
    (tmp_path / "sample/model/entities.py").write_text(
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Order:\n"
        "    order_id: str\n"
    )
    # Violation: a dataclass declared outside the one allowed module.
    (tmp_path / "sample/model/rogue.py").write_text(
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Coupon:\n"
        "    code: str\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids, item.subjects) for item in violations] == [
        (
            "symbol_placement",
            ("MODEL-TYPES-IN-ENTITIES",),
            ("sample.model.rogue", "sample.model.rogue.Coupon"),
        )
    ]


def _boundary_types_contract(*components: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "components": list(components),
        "rules": [
            {
                "id": "APP-TYPES-NOT-DICT",
                "kind": "boundary_types",
                "source": "sample.app",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }


def test_boundary_types_checks_only_the_declared_facade(tmp_path: Path) -> None:
    """AD-63: a naming convention used to check every non-underscore function below `source`;
    now only a function `component.public` itself names is inspected (issue #44). Before this
    change, `internal`'s bare `dict` was also reported; it is silent now because `app` never
    declared it as part of its facade, even though it is neither underscore nor out of scope.
    """
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:snapshot"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "def snapshot(context: dict) -> str:\n"
        "    return str(context)\n\n\n"
        "def internal(context: dict) -> str:\n"
        "    return str(context)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids, item.subjects) for item in violations] == [
        (
            "boundary_types",
            ("APP-TYPES-NOT-DICT",),
            ("sample.app.facade", "sample.app.facade.snapshot"),
        )
    ]


def test_boundary_types_reports_a_type_the_facade_does_not_declare(tmp_path: Path) -> None:
    """AD-63: a bare name now resolves through the same import bindings `interface_boundary`
    reads; a resolved type that is neither a builtin, an enum, a Pydantic model, nor declared
    by any component's own `public` list is the leak issue #9 asked this rule to catch."""
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:broken"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "class Payload:\n"
        "    pass\n\n\n"
        # Payload is defined right here and never declared in app's public list: a genuine
        # undeclared type crossing the facade, not a naming-convention artefact.
        "def broken(payload: Payload) -> str:\n"
        "    return str(payload)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids, item.subjects) for item in violations] == [
        (
            "boundary_types",
            ("APP-TYPES-NOT-DICT",),
            ("sample.app.facade", "sample.app.facade.broken"),
        )
    ]


def test_boundary_types_is_silent_when_the_facade_declares_the_named_type(tmp_path: Path) -> None:
    """AD-63: a type app's own facade declares is exactly the pattern issue #9 asked for."""
    contract = _boundary_types_contract(
        _component("app", public=["sample.app.facade:typed", "sample.app.facade:Order"])
    )
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "class Order:\n    pass\n\n\ndef typed(order: Order) -> Order:\n    return order\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()


def test_boundary_types_is_silent_for_a_provider_returning_its_own_declared_type(
    tmp_path: Path,
) -> None:
    """AD-63 amends AD-58: `archkeel.analyzer.observe` returning `ir`'s own `ObservationResult`
    and `shop.render.text.render_order` returning `shop.model`'s own `Order` are the two false
    positives AD-58's measurement found and rejected the contract reading over; here `core`, not
    `app`, declares `Order` public, and app's own facade function still returns it cleanly,
    because the declared facade is read component-wide, not only against app's own list."""
    contract = _boundary_types_contract(
        _component("app", public=["sample.app.facade:typed"]),
        _component("core", public=["sample.core.model:Order"]),
    )
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "from sample.core.model import Order\n\n\n"
        "def typed(order: Order) -> Order:\n"
        "    return order\n"
    )
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/core/__init__.py").write_text("")
    (tmp_path / "sample/core/model.py").write_text("class Order:\n    pass\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()


def test_boundary_types_is_silent_for_an_enum_even_when_undeclared(tmp_path: Path) -> None:
    """AD-63: `enum` and `pydantic_model` cross a boundary self-describing, so they clear a
    facade function even when nobody declared them (issue #9's own phrasing)."""
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:snapshot"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "from enum import StrEnum\n\n\n"
        "class Status(StrEnum):\n"
        '    OPEN = "open"\n\n\n'
        "def snapshot(status: Status) -> str:\n"
        "    return status.value\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()


def _facade_types(observation: Observation) -> dict[str, tuple[str, ...]]:
    """Every function symbol that records the types its declared facade signature exposes."""
    return {
        name: types
        for record in observation.records("symbols") or ()
        if (name := text_value(record.data.get("qualified_name")))
        and isinstance(types := record.data.get("facade_types"), tuple)
    }


def test_a_declared_facade_records_the_types_its_signature_exposes(tmp_path: Path) -> None:
    """AD-65: `Widget` reaches `app`'s boundary through `typed`'s parameter, although no other
    component imports it. The resolution is `boundary_types`' own (AD-63), recorded whether or
    not a `boundary_types` rule is declared -- this contract declares none -- because
    `interface_boundary` asks the same question of every component that declares a facade.
    """
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("app", public=["sample.app.facade:typed"])],
        "rules": [],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/ports.py").write_text("class Widget:\n    pass\n")
    (tmp_path / "sample/app/facade.py").write_text(
        "from sample.app.ports import Widget\n\n\n"
        "def typed(widget: Widget) -> str:\n"
        "    return str(widget)\n\n\n"
        "def internal(widget: Widget) -> str:\n"
        "    return str(widget)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _facade_types(result.observation) == {
        "sample.app.facade.typed": ("sample.app.ports.Widget",)
    }


def test_an_unresolved_facade_annotation_records_no_type(tmp_path: Path) -> None:
    """AD-65's limit: the rule's own unresolved bucket (AD-63) stays silent here too. A
    builtin needs no import, and a dotted name is never resolved, so neither reaches an entry
    and neither is recorded as though it did."""
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("app", public=["sample.app.facade:typed"])],
        "rules": [],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "import sample.app.ports\n\n\n"
        "def typed(count: int) -> sample.app.ports.Widget:\n"
        "    return count\n"
    )
    (tmp_path / "sample/app/ports.py").write_text("class Widget:\n    pass\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _facade_types(result.observation) == {}


def test_boundary_types_reports_unknown_when_the_facade_has_no_subjects(tmp_path: Path) -> None:
    """Issue #56: a component with no declared public gives boundary_types zero functions to
    check, and reading no violations back as a clean pass would be the same defect #43 fixed
    for a different rule -- a declared rule that cannot fail. `source` matching a scanned
    module used to be enough (any non-underscore function under it was a subject); AD-63's own
    narrowing makes that no longer true for this one rule kind, so rule_subject_failures now
    reads the declared facade too, not just module names, and reports rule-without-subjects
    instead of silence.
    """
    contract = _boundary_types_contract(_component("app"))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "def snapshot(context: dict) -> str:\n    return str(context)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    unknowns = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.rule_ids == ("APP-TYPES-NOT-DICT",)
    ]
    assert [item.kind for item in unknowns] == ["rule-without-subjects"]
    assert result.observation.coverage.rules == "FAIL"
    assert result.diagnostics and result.diagnostics[0].kind == "rule_without_subjects"
    assert result.exit_code == 2


def test_boundary_types_planned_facade_is_target_work_not_unknown(tmp_path: Path) -> None:
    """#79: a scanned planned facade is a visible target, not an empty rule scope."""
    contract = _boundary_types_contract(_component("app", planned=["sample.app.facade:snapshot"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "def snapshot(context: dict) -> str:\n    return str(context)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    assert not any(
        item.kind == "rule-without-subjects"
        for item in result.observation.records("unknowns") or ()
    )
    assert result.exit_code == 0


def test_boundary_types_unscanned_planned_facade_is_target_work(tmp_path: Path) -> None:
    """#79: an exact planned scope is target work before its module exists."""
    contract = _boundary_types_contract(_component("app", planned=["sample.app.future:snapshot"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "def unrelated(context: dict) -> str:\n    return str(context)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert not any(
        item.kind == "rule-without-subjects"
        for item in result.observation.records("unknowns") or ()
    )
    assert result.exit_code == 0


def test_planned_facade_does_not_explain_an_unrelated_rule_scope(tmp_path: Path) -> None:
    """#79: a scope with no matching planned entry still fails closed."""
    contract = _boundary_types_contract(_component("app", planned=["sample.app.future:snapshot"]))
    contract["rules"][0]["source"] = "sample.app.typo"
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert any(
        item.kind == "rule-without-subjects"
        for item in result.observation.records("unknowns") or ()
    )
    assert result.exit_code == 2


def test_unscanned_planned_module_explains_a_general_rule_scope(tmp_path: Path) -> None:
    """#79: planned subjects apply to rules beyond boundary_types."""
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("app", planned=["sample.app.future:snapshot"])],
        "rules": [
            {
                "id": "NO-GETATTR",
                "kind": "forbidden_construct",
                "source": "sample.app.future",
                "constructs": ["getattr"],
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert not any(
        item.kind == "rule-without-subjects"
        for item in result.observation.records("unknowns") or ()
    )
    assert result.exit_code == 0


def test_boundary_types_reports_a_position_it_could_not_decide(tmp_path: Path) -> None:
    """AD-67: an undecidable position produced nothing at all, so the rule's verdict read
    `no violation == probably fine` while the rest of the tool reads PASS/VIOLATION/UNKNOWN
    (AD-26). The rule now names its own denominator the way `dynamic_call_limit` names the
    call graph's: how many positions it saw, how many it decided, and how many of each
    undecidable kind it left. `str` and `int` decide; `datetime.datetime` is a dotted name and
    `'Later'` a forward reference, and neither resolves to a `(module, name)` this rule can
    judge.
    """
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:mixed"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "import datetime\n\n\n"
        "class Later:\n"
        "    pass\n\n\n"
        "def mixed(name: str, when: datetime.datetime, note: 'Later', spare) -> int:\n"
        "    return len(name) + len(str(when)) + len(str(note)) + len(str(spare))\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    limits = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    ]
    assert [item.rule_ids for item in limits] == [("APP-TYPES-NOT-DICT",)]
    data = limits[0].data
    assert (data.get("positions"), data.get("decided"), data.get("undecided")) == (5, 2, 3)
    assert data.get("dotted_name") == 1
    assert data.get("forward_reference") == 1
    assert data.get("missing_annotation") == 1
    # A position the rule cannot decide is a reported limit, not a gate: the run stays clean
    # and the rule still holds a verdict, because it decided the positions it could.
    assert result.observation.coverage.rules == "PASS"
    assert result.diagnostics == ()
    assert result.exit_code == 0


def test_boundary_types_decides_a_bare_name_inside_a_collection(tmp_path: Path) -> None:
    """AD-67: the same mistake used to disappear by being wrapped -- `payload: Payload` was
    reported and `payloads: list[Payload]` was silent, because a generic's parameters were
    never inspected, so refactoring a parameter into a list silently dropped the check. A
    known collection holding a bare name is now the resolution `boundary_types` already runs,
    applied one level in; `tuple[str, ...]` decides clean on the builtin, and
    `list[datetime.datetime]` stays undecidable because a dotted name still is.
    """
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:broken"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "import datetime\n\n\n"
        "class Payload:\n"
        "    pass\n\n\n"
        "def broken(\n"
        "    payloads: list[Payload], names: tuple[str, ...], "
        "stamps: list[datetime.datetime]\n"
        ") -> set[Payload]:\n"
        "    return {*payloads, *names, *stamps}\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [item.title for item in violations] == [
        "sample.app.facade.broken returns set[Payload] holding Payload which app does not declare",
        "sample.app.facade.broken takes payloads as list[Payload] holding Payload "
        "which app does not declare",
    ]
    limits = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    ]
    data = limits[0].data
    assert (data.get("positions"), data.get("decided"), data.get("undecided")) == (4, 3, 1)
    # Entered, so the position is undecidable for its element's own reason, not for being a
    # generic: `list[datetime.datetime]` is a dotted name the rule cannot resolve.
    assert (data.get("dotted_name"), data.get("generic")) == (1, 0)


def test_a_function_used_only_as_a_value_is_recorded_as_a_reference(tmp_path: Path) -> None:
    """AD-26: a call graph cannot see a function handed to a dict; the reference signal can."""
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("core"), _component("cli")],
        "rules": [
            {
                "id": "DEP-CLI-ALLOWS-CORE",
                "kind": "allowed_dependency",
                "source": "sample.cli",
                "target": "sample.core",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
            {
                "id": "DEP-CORE-NO-CLI",
                "kind": "forbidden_dependency",
                "source": "sample.core",
                "target": "sample.cli",
                "include_type_checking": True,
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
        ],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text("def handler() -> int:\n    return 1\n")
    # The handler is never called here; it is put into a table, which no call site names.
    (tmp_path / "sample/cli.py").write_text(
        'from sample.core import handler\n\nHANDLERS = {"a": handler}\n'
    )
    result = _observe(tmp_path)
    assert result.observation is not None

    references = result.observation.records("references") or ()
    targets = {target for record in references for target in (record.data.get("targets") or [])}
    assert "sample.core.handler" in targets
    calls = result.observation.records("calls") or ()
    assert not [item for item in calls if "sample.core.handler" in (item.data.get("targets") or [])]


def test_a_binding_the_body_never_reads_is_recorded(tmp_path: Path) -> None:
    """AD-26: a dead binding is settled in one scope, so the function's own tree answers it.

    The expected set also states the exemptions, by leaving them out: `_reserved` carries
    Python's own mark for a deliberately unused name, `self` is bound by the call convention,
    and `Child.handle` must keep the signature it overrides.
    """
    contract = {"schema_version": "2.1.0", "components": [_component("core")], "rules": []}
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "def summarise(amount: int, currency: str, _reserved: int) -> str:\n"
        '    label = "total"\n'
        "    spare = amount * 2\n"
        '    return f"{label}: {amount}"\n\n\n'
        "class Base:\n"
        "    def handle(self, value: int) -> int:\n"
        "        return value\n\n\n"
        "class Child(Base):\n"
        "    def handle(self, value: int) -> int:\n"
        "        return 0\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None

    bindings = result.observation.records("bindings") or ()
    assert {(item.kind, item.data.get("name")) for item in bindings} == {
        ("unused_parameter", "currency"),
        ("unused_local", "spare"),
    }


@pytest.mark.parametrize(
    ("source", "expression", "status", "targets", "reason"),
    [
        (
            "import hashlib\n\n\ndef f(payload: bytes) -> None:\n"
            "    digest = hashlib.sha256()\n    digest.update(payload)\n",
            "digest.update",
            "partially_resolved",
            ["hashlib._Hash.update"],
            "receiver bound to a call result of documented type, unproven at runtime",
        ),
        (
            "import hashlib\n\n\ndef f(payload: bytes) -> str:\n"
            "    return hashlib.sha256(payload).hexdigest()\n",
            "hashlib.sha256(payload).hexdigest",
            "partially_resolved",
            ["hashlib._Hash.hexdigest"],
            "call result of documented type, unproven at runtime",
        ),
        (
            "import argparse\n\n\ndef f() -> None:\n"
            "    parser = argparse.ArgumentParser()\n"
            '    commands = parser.add_subparsers(dest="command")\n'
            '    check = commands.add_parser("check")\n'
            '    check.add_argument("--root")\n',
            "check.add_argument",
            "partially_resolved",
            ["argparse.ArgumentParser.add_argument"],
            "receiver bound to a call result of documented type, unproven at runtime",
        ),
        (
            "from rich.table import Table\n\n\ndef f() -> None:\n"
            '    verdicts = Table(title="verdicts")\n    verdicts.add_column("check")\n',
            "verdicts.add_column",
            "partially_resolved",
            ["rich.table.Table.add_column"],
            "receiver bound to a call result of documented type, unproven at runtime",
        ),
        (
            "class Table:\n    def add_column(self, name: str) -> None:\n        pass\n\n\n"
            'def f() -> None:\n    verdicts = Table()\n    verdicts.add_column("check")\n',
            "verdicts.add_column",
            "partially_resolved",
            ["sample.mod.Table.add_column"],
            "dynamic receiver with matching internal methods",
        ),
    ],
)
def test_call_results_of_documented_type_resolve_their_methods(
    source: str, expression: str, status: str, targets: list[str], reason: str
) -> None:
    """AD-40: a constructor the import binding proves, or a documented return, types a call.

    The last row is the guard: a project's own `Table` is not an import binding, so it never
    borrows Rich's method table and keeps the answer the symbol index gives it.
    """
    module = _parsed_module(source)
    symbols, _, _ = collect_symbols([module], {})
    index = build_symbol_index(symbols)
    collect_imports([module], set(), {}, namespace="sample")
    calls = collect_calls([module], index, {})
    match = next(item for item in calls if item["data"]["expression"] == expression)
    assert match["data"]["status"] == status
    assert match["data"]["targets"] == targets
    assert match["data"]["reason"] == reason


def test_a_requires_entry_covers_only_the_modules_it_goes_through() -> None:
    """AD-42: `through` narrows a `requires` entry to module prefixes of the required component.

    `cli` requires `core` through `sample.core.model`, so importing `sample.core.model` is
    covered and importing `sample.core.store` is the violation an unrequired component gets.
    """
    entry = {
        "component": "core",
        "through": ["sample.core.model"],
        "rationale": "The composition root reads the model, never the store.",
    }
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli") | {"requires": [entry]}],
            "rules": [_INNER_REQUIRES_RULE],
        }
    )
    module = _parsed_module(
        "import sample.core.model\nimport sample.core.store\n", module="sample.cli.main"
    )
    imports = collect_imports(
        [module], {"sample.core.model", "sample.core.store"}, {}, namespace="sample"
    )
    violations = requires_violations(imports, contract)
    assert [item["data"]["target_module"] for item in violations] == ["sample.core.store"]
    assert violations[0]["rule_ids"] == ["REQUIRES-COMPLETE"]


def test_from_import_binds_the_package_attribute_over_a_same_named_submodule() -> None:
    """AD-53 / issue #23: `from pkg import name` binds what `pkg/__init__.py` binds first.

    `pkg` assigns `name` to a string at module scope, so CPython's `_handle_fromlist` finds
    the attribute through `hasattr` before it ever imports the submodule `pkg/name.py`. Before
    AD-53 the scan alone decided this: since `pkg.name` was a scanned module, the import was
    recorded as the module `pkg.name`, though the program never touches that file.
    """
    package_init = _parsed_module(
        'name = "something"\n', module="pkg", rel_path="pkg/__init__.py", package="pkg"
    )
    submodule = _parsed_module(
        "VALUE = 1\n", module="pkg.name", rel_path="pkg/name.py", package="pkg"
    )
    consumer = _parsed_module(
        "from pkg import name\n", module="app", rel_path="app.py", package="app"
    )
    imports = collect_imports(
        [package_init, submodule, consumer], {"pkg", "pkg.name", "app"}, {}, namespace="pkg"
    )
    [record] = [item for item in imports if item["data"]["source_module"] == "app"]
    assert record["data"]["target_module"] == "pkg"
    assert record["data"]["symbol"] == "name"


def test_from_import_of_a_re_exported_submodule_still_resolves_to_the_submodule() -> None:
    """AD-53's precedence must not over-correct the common `from . import name` re-export.

    `pkg/__init__.py` binds `name` by importing the submodule itself, so the attribute Python
    finds *is* the submodule `pkg.name`; the fix keeps the pre-existing, correct reading here.
    """
    package_init = _parsed_module(
        "from . import name\n", module="pkg", rel_path="pkg/__init__.py", package="pkg"
    )
    submodule = _parsed_module(
        "VALUE = 1\n", module="pkg.name", rel_path="pkg/name.py", package="pkg"
    )
    consumer = _parsed_module(
        "from pkg import name\n", module="app", rel_path="app.py", package="app"
    )
    imports = collect_imports(
        [package_init, submodule, consumer], {"pkg", "pkg.name", "app"}, {}, namespace="pkg"
    )
    [record] = [item for item in imports if item["data"]["source_module"] == "app"]
    assert record["data"]["target_module"] == "pkg.name"
    assert record["data"]["symbol"] is None


def test_facade_types_resolve_a_collection_element(tmp_path: Path) -> None:
    """AD-69: the two readers of one annotation agree, including one level into a collection.

    `boundary_types` judges the element of a `tuple[Widget, ...]` (AD-67). If reachability read
    bare names only, declaring `Widget` would satisfy the rule and be called `interface.unused`
    by the same run: the drift AD-65 removed, one subscript deeper.
    """
    contract = {
        "schema_version": "2.1.0",
        "components": [_component("app", public=["sample.app.facade:typed"])],
        "rules": [],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/ports.py").write_text("class Widget:\n    pass\n")
    (tmp_path / "sample/app/facade.py").write_text(
        "from sample.app.ports import Widget\n\n\n"
        "def typed(widgets: tuple[Widget, ...]) -> list[Widget]:\n"
        "    return list(widgets)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _facade_types(result.observation) == {
        "sample.app.facade.typed": ("sample.app.ports.Widget",)
    }


def test_boundary_types_and_facade_types_agree_across_annotation_shapes(tmp_path: Path) -> None:
    """Regression guard (green today): `boundary_types` and `facade_types` are two readers of
    the same `typed` signature (AD-69), and this pins that they agree on every shape below,
    including agreeing on silence -- not merely that a refactor happened (the structural tests
    above pin that), but that the two readings still land on the same answer.

    Every `PayloadN` class lives in `facade.py` itself and is left off `app`'s declared
    `public` list, so whenever the rule actually resolves a position to a named type, that type
    is undeclared and the position is *always* a `boundary_types` violation -- never a builtin,
    an enum, or a declared type. That lets "the rule resolved type T at this position" be read
    off an observable violation (`position` in its `data`) rather than a private helper's
    return value, and compared against "`facade_types` records T for this function"
    (`_facade_types`). If either reader is later taught a shape the other is not -- entering
    `Mapping[...]`, unwrapping `X | None`, walking a second subscript level -- the row for that
    shape flips from agreement to disagreement and this test catches it.
    """
    contract = _boundary_types_contract(_component("app", public=["sample.app.facade:typed"]))
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text("")
    (tmp_path / "sample/app/facade.py").write_text(
        "from collections.abc import Mapping\n"
        "from typing import Optional\n"
        "import datetime\n\n\n"
        "class Payload1:\n    pass\n\n\n"
        "class Payload2:\n    pass\n\n\n"
        "class Payload3:\n    pass\n\n\n"
        "class Payload4a:\n    pass\n\n\n"
        "class Payload4b:\n    pass\n\n\n"
        "class Payload5:\n    pass\n\n\n"
        "class Payload6:\n    pass\n\n\n"
        "class Payload7:\n    pass\n\n\n"
        "def typed(\n"
        "    payload1: Payload1,\n"
        "    payload2: tuple[Payload2, ...],\n"
        "    payload3: list[Payload3],\n"
        "    union4: Payload4a | Payload4b,\n"
        "    mapping5: Mapping[str, Payload5],\n"
        "    optional6: Optional[Payload6],\n"
        "    nested7: list[list[Payload7]],\n"
        "    dotted8: datetime.datetime,\n"
        "    forward9: 'Payload9',\n"
        ") -> str:\n"
        "    return ''\n\n\n"
        "class Payload9:\n"
        "    pass\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None

    qualname = "sample.app.facade.typed"
    violated_positions = {
        item.data.get("position")
        for item in trace_valid_violations(result.observation)
        if item.kind == "boundary_types" and item.data.get("qualified_name") == qualname
    }
    facade_types = set(_facade_types(result.observation).get(qualname, ()))

    # One shape per row: the candidate type(s) the rule would have to resolve, at that
    # position, for facade_types to have any business recording them. Bare names and one level
    # into a known collection resolve on both sides; a union, an unentered generic (`Mapping`,
    # `Optional`), a second subscript level, a dotted attribute and a quoted forward reference
    # resolve on neither (AD-67, AD-69's own Limit).
    shapes: dict[str, tuple[str, ...]] = {
        "payload1": ("sample.app.facade.Payload1",),
        "payload2": ("sample.app.facade.Payload2",),
        "payload3": ("sample.app.facade.Payload3",),
        "union4": ("sample.app.facade.Payload4a", "sample.app.facade.Payload4b"),
        "mapping5": ("sample.app.facade.Payload5",),
        "optional6": ("sample.app.facade.Payload6",),
        "nested7": ("sample.app.facade.Payload7",),
        "dotted8": ("datetime.datetime",),
        "forward9": ("sample.app.facade.Payload9",),
    }
    disagreements = []
    for position, candidates in shapes.items():
        rule_resolved = position in violated_positions
        for candidate in candidates:
            facade_resolved = candidate in facade_types
            if rule_resolved != facade_resolved:
                disagreements.append(
                    f"{position} ({candidate}): boundary_types "
                    f"{'resolved' if rule_resolved else 'left silent'} this position while "
                    f"facade_types {'recorded' if facade_resolved else 'left out'} {candidate}"
                )
    assert disagreements == []
    # A fixture where every row agreed by staying silent would pass vacuously; at least one
    # shape must actually be resolved on both sides for the agreement above to mean anything.
    assert violated_positions, (
        "no shape here was decided at all -- the agreement check above is vacuous"
    )


def _violations_source_ast() -> ast.Module:
    return ast.parse((EMBEDDED / "violations.py").read_bytes())


def _top_level_callers(tree: ast.Module, called_name: str) -> set[str]:
    """The module-level functions whose body directly calls `called_name`.

    Walking only a top-level `FunctionDef`'s own subtree, rather than the whole module, is what
    tells "one function calls this" apart from "this name merely appears in the file" -- and
    doing it over `ast` rather than a text search is what tells a real call apart from the name
    showing up in a docstring or a comment.
    """
    return {
        node.name
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, ast.FunctionDef)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == called_name
    }


def test_only_one_function_resolves_an_annotations_named_type() -> None:
    """AD-69 hand-synced two readers instead of merging them into one (the drift it names as
    already having happened once, over `list[Type]`). `_boundary_type_verdict` (the
    `boundary_types` rule) and `_resolved_position_types` (the `facade_types` reachability
    reading) each call `_resolve_named_type` on their own candidate string, so a future
    annotation shape -- `A | B`, `Mapping[str, A]`, `Optional[A]` -- has to be taught to both
    call sites by hand, or the readings drift apart again. One shared analysis per annotation
    means exactly one function in this module ever calls `_resolve_named_type`; a second caller
    is the duplicated interpretation this pins against.
    """
    callers = _top_level_callers(_violations_source_ast(), "resolve_named_type")
    assert len(callers) == 1, (
        f"resolve_named_type is called directly from {sorted(callers)}: more than one "
        "function derives a resolved type from an annotation, instead of one shared analysis "
        "both `boundary_types` and `facade_types` read."
    )


def test_resolved_position_types_does_not_itself_walk_collection_parameters() -> None:
    """The reachability reading must not re-implement "enter one level of a known collection":
    that decision is `_collection_verdict`'s, made for the `boundary_types` rule. Today
    `_resolved_position_types` calls `_collection_parameters` itself to build its own candidate
    list, which is exactly the second, hand-kept copy of that decision AD-69 introduced to fix
    `list[Type]`; a new collection shape taught only to the rule would again go silent on this
    side, the same way `list[Type]` once did.
    """
    tree = _violations_source_ast()
    [target] = [
        node
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_resolved_position_types"
    ]
    walks_collections = any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_collection_parameters"
        for call in ast.walk(target)
    )
    assert not walks_collections, (
        "_resolved_position_types calls _collection_parameters itself: it derives which "
        "positions to resolve on its own, instead of reading the one analysis "
        "_boundary_type_verdict already computed for the same annotation."
    )
