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
from archkeel.analyzer.embedded.constructs import collect_constructs
from archkeel.analyzer.embedded.source import ParsedModule
from archkeel.check.validation import COMPONENT_GRAPH_MARKER, observation_diagnostics
from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.interfaces import component_owners
from archkeel.ir.model import Coverage, Diagnostic, Observation
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


def _component(label: str, *, public: list[str] | None = None) -> dict[str, object]:
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


def _with_inside(tmp_path: Path, inside: str) -> None:
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
                "rules": [],
            }
        )
    )


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
    assert records["core:COMP-A"].data.get("requires") == ("b",)
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
    ],
)
def test_class_a_rule_produces_one_traceable_violation(
    tmp_path: Path, rule: dict[str, object], sources: dict[str, str]
) -> None:
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
    result = _observe(tmp_path)
    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert [(item.kind, item.rule_ids) for item in violations] == [(rule["kind"], ("RULE",))]
    assert len(result.observation.records("violations") or ()) == 1


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


def _parsed_module(source: str, module: str = "sample.mod") -> ParsedModule:
    return ParsedModule(
        path=Path("sample/mod.py"),
        rel_path="sample/mod.py",
        module=module,
        package="sample",
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
