# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-285: `archkeel explore` shows the as-is code of a repository that has no contract."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from rich.console import Console
from test_result_schema import _validator

from archkeel.analyzer.python.collect import PythonProviderCollector
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_observation
from archkeel.ir.diagnostics import Diagnostic
from archkeel.ir.model import Command, DiagnosticCode, DiagnosticKind, ObservationResult, RunResult
from archkeel.ir.report_graph import architecture_report
from archkeel.render.summary import report_summary
from archkeel.render.terminal import print_result
from fixtures.architecture_demo import CATALOG, replay
from fixtures.architecture_demo import main as demo_main
from fixtures.demo_catalog_dart import DART_FIXTURE_DIR
from fixtures.demo_catalog_explore import (
    EXPLORE_FIXTURE_DIR,
    nested_engine_files,
)
from fixtures.demo_catalog_explore import (
    VARIANTS as EXPLORE_VARIANTS,
)
from fixtures.demo_catalog_typescript import VARIANTS as TYPESCRIPT_VARIANTS
from fixtures.reproduce_typescript import repository as typescript_repository

_SOURCES = {
    "shop/__init__.py": "",
    "shop/app/__init__.py": "",
    "shop/app/orders.py": (
        "from shop.store.repository import save\n\n\ndef place() -> int:\n    return save(1)\n"
    ),
    "shop/store/__init__.py": "",
    "shop/store/repository.py": "def save(value: int) -> int:\n    return value\n",
    "shop/cli/__init__.py": "",
    "shop/cli/__main__.py": "from shop.app.orders import place\n\nplace()\n",
    "pyproject.toml": '[project]\nname = "shop"\nrequires-python = ">=3.11"\n',
}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def _repository(root: Path, files: dict[str, str] = _SOURCES, *, commit: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "explore@example.invalid")
    _git(root, "config", "user.name", "Archkeel explore")
    if commit:
        _git(root, "add", ".")
        _git(root, "commit", "-qm", "snapshot", "--allow-empty")
    return root


def _repository_with_symlink(root: Path, files: dict[str, str], link: str, target: str) -> Path:
    repository = _repository(root, files, commit=False)
    try:
        link_path = repository / link
        target_path = repository / target
        link_path.symlink_to(
            os.path.relpath(target_path, link_path.parent), target_is_directory=target_path.is_dir()
        )
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unavailable: {error}")
    _git(repository, "add", ".")
    _git(repository, "commit", "-qm", "snapshot")
    return repository


def _explore(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, dict]:
    code = main(["explore", *args, "--json"])
    return code, json.loads(capsys.readouterr().out)


def _snapshot(path: Path):
    return parse_observation(decode_canonical_model(decode_json(path.read_bytes())))


def _tree_digest(root: Path) -> dict[str, str]:
    """Every file below the root, ignored ones too; Git's own folder is not repository content."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def test_explore_shows_a_repository_without_a_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "repo")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    code, payload = _explore(capsys, "--root", str(root))

    assert code == 0, payload
    assert payload["target"] == "unavailable"
    assert payload["declared_rules"] == "UNKNOWN"
    assert payload["rule_assessments"] == []
    assert payload["open_decisions"] == []
    assert payload["scan_roots"] == ["shop"]
    validator = _validator("command-result-11.0.schema.json")
    assert validator.is_valid(payload)
    assert not validator.is_valid({**payload, "declared_rules": "PASS"})
    key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    artifact = tmp_path / "cache" / "archkeel" / "explore" / key / "architecture.json"
    assert payload["artifact"] == str(artifact)
    assert (payload["root_name"], payload["root_digest"]) == ("repo", key)
    raw = artifact.read_bytes()
    assert str(root.resolve()).encode() not in raw
    # The layout is observed by explore; no architecture page exists to cite.
    assert b"docs/architecture/architecture.md" not in raw
    model = _snapshot(artifact)
    assert model.contract.path == "archkeel-explore-layout.json"
    memberships = {item.component_id for item in architecture_report(model).memberships}
    assert memberships == {"COMP-APP", "COMP-CLI", "COMP-STORE"}
    page = artifact.with_name("architecture.report.html").read_text()
    assert page.index('id="inventory-heading"') < page.index('id="findings-heading"')
    assert "Target unavailable: no rule is declared, so no rule passes or fails" in page
    assert "3 layout components" in page
    inventory = page[page.index('id="inventory-heading"') : page.index('id="findings-heading"')]
    # AD-285: only one line is open, so the Explorer stays on the first screen.
    assert "<code>store</code> (2)" in inventory
    assert inventory.index("<details") < inventory.index("<table")
    assert "shop.cli.__main__" in page
    assert "PASS · Rules" not in page
    # AD-285: no PASS beside "no rule passes", no violation and no Target view without a target.
    assert "Source observation complete" in page
    detail = artifact.with_name("architecture.detail.html").read_text().split('id="flow-data"')[0]
    assert "Target unavailable: no rule is declared" in detail
    assert "Whole-run rules" not in detail
    assert "<p>No dependency cycle or hub.</p>" in page
    assert '[data-flow-view="target"],[data-flow-view="diff"],.flow-violation-focus' in page


def test_root_package_with_rust_only_src_demo_uses_root_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "architecture.json"

    assert (
        demo_main(["--replay", "explore-root-package-with-rust-src", "--output", str(output)]) == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["scan_roots"] == ["shop"]


def test_typescript_explore_demo_sets_a_finite_collector_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "architecture.json"
    variant = next(
        item for item in EXPLORE_VARIANTS if item.id == "explore-typescript-explicit-output-limit"
    )

    assert replay(variant.id, output) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["observation_complete"] == "PASS"
    assert output.is_file()


def test_typescript_v8_transport_demo_fits_an_8_kib_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "architecture.json"
    variant = next(item for item in EXPLORE_VARIANTS if item.id == "explore-typescript-v8-8kib")

    assert replay(variant.id, output) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["observation_complete"] == "PASS"
    assert output.is_file()


def test_explore_never_writes_into_the_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "repo")
    (root / ".gitignore").write_text("ignored.txt\n")
    (root / "ignored.txt").write_text("kept\n")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    tree, status = _tree_digest(root), _git(root, "status", "--porcelain", "--ignored")

    assert _explore(capsys, "--root", str(root))[0] == 0
    code, payload = _explore(capsys, "--root", str(root), "--output", str(root / "out"))

    assert code == 2
    assert "inside the analyzed repository" in payload["diagnostics"][0]["unknown_claim"]
    assert _tree_digest(root) == tree
    assert _git(root, "status", "--porcelain", "--ignored") == status


def test_a_saved_explore_snapshot_gives_no_rule_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo")
    assert _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))[0] == 0
    snapshot = str(tmp_path / "out" / "architecture.json")

    assert main(["report", "--input", snapshot, "--json"]) == 0
    saved = json.loads(capsys.readouterr().out)
    query = ["report", "--input", snapshot, "--only", "architecture", "--component", "COMP-STORE"]
    assert main([*query, "--json"]) == 0
    component = json.loads(capsys.readouterr().out)

    assert (saved["target"], saved["declared_rules"]) == ("unavailable", "UNKNOWN")
    assert component["declared_rules"] == "UNKNOWN"
    assert [item["id"] for item in component["architecture_projection"]["components"]] == [
        "COMP-STORE"
    ]
    query[-1] = "COMP-NOPE"
    assert main([*query, "--json"]) == 2
    fabricated = json.loads(capsys.readouterr().out)
    assert [item["kind"] for item in fabricated["diagnostics"]] == ["filter_unknown"]


def test_explore_records_the_worktree_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo")
    output = tmp_path / "out"
    assert _explore(capsys, "--root", str(root), "--output", str(output))[0] == 0
    clean = _snapshot(output / "architecture.json").source
    (root / "shop/store/repository.py").write_text("def save(value: int) -> int:\n    return 2\n")

    assert _explore(capsys, "--root", str(root), "--output", str(output))[0] == 0
    dirty = _snapshot(output / "architecture.json").source

    assert (clean.dirty, dirty.dirty) == (False, True)
    assert clean.git_head == dirty.git_head
    assert clean.source_digest != dirty.source_digest


@pytest.mark.parametrize(
    ("marker", "named"),
    [(None, "none"), ("tsconfig.json", "tsconfig.json"), ("pubspec.yaml", "pubspec.yaml")],
)
def test_explore_without_a_python_package_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], marker: str | None, named: str
) -> None:
    root = _repository(tmp_path / "repo", {marker: "{}\n"} if marker else {})
    output = tmp_path / "out"
    output.mkdir()
    (output / "architecture.json").write_text("{}")

    code, payload = _explore(capsys, "--root", str(root), "--output", str(output))

    assert code == 2
    [diagnostic] = payload["diagnostics"]
    assert diagnostic["kind"] == "scope_empty"
    assert named in diagnostic["unknown_claim"]
    # AD-285: a failed scope check deletes nothing, and the result names no absolute path.
    assert (output / "architecture.json").read_text() == "{}"
    assert str(tmp_path) not in json.dumps(payload)


def test_explore_without_a_commit_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo", commit=False)

    code, payload = _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))

    assert code == 2
    assert "Git commit" in payload["diagnostics"][0]["remedy"]


def test_explore_collects_the_source_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The nested levels add inside contracts; the second pass must still reuse the facts.
    root = _repository(tmp_path / "repo", {**_SOURCES, **nested_engine_files()})
    collect = PythonProviderCollector.collect
    calls: list[object] = []

    def counted(self: PythonProviderCollector, request: object):  # type: ignore[no-untyped-def]
        calls.append(request)
        return collect(self, request)  # type: ignore[arg-type]

    monkeypatch.setattr(PythonProviderCollector, "collect", counted)

    assert _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))[0] == 0
    assert len(calls) == 1


def test_report_on_a_contract_without_a_rule_gives_no_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _zero_rule_repository(tmp_path / "repo")

    code = main(["report", "--root", str(root), "--output", str(tmp_path / "a.json"), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert (payload["target"], payload["declared_rules"]) == ("unavailable", "UNKNOWN")


def test_the_explore_demo_row_replays_without_a_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    variant = next(item for item in CATALOG if item.id == "explore-contract-free")
    artifact = tmp_path / "explore" / "architecture.json"

    assert replay(variant.id, artifact) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["declared_rules"] == variant.expected_declared_rules
    assert payload["target"] == "unavailable"
    assert 'id="inventory-heading"' in artifact.with_name("architecture.report.html").read_text()
    assert not (variant.fixture / "archkeel.toml").exists()


def _zero_rule_repository(root: Path, **intent: object) -> Path:
    contract = {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": "COMP-SHOP",
                "label": "shop",
                "role": "component",
                "packages": ["shop"],
                "responsibilities": [],
                "forbidden_responsibilities": [],
                "provenance": ["docs/architecture.md"],
                **intent,
            }
        ],
        "rules": [],
    }
    files = {
        **_SOURCES,
        "docs/architecture.md": "# Architecture\n\n<!-- archkeel-component-graph -->\n"
        "```mermaid\ngraph TD\n```\n",
        "architecture-contract.json": json.dumps(contract),
        "archkeel.toml": '[scan]\nroots = ["shop"]\nnamespace = "shop"\n'
        'contract = "architecture-contract.json"\n',
    }
    return _repository(root, files)


def test_an_invalid_contract_shows_its_diagnostics_and_no_target_label(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    assert main(["explore", "--root", str(root), "--output", str(tmp_path / "out"), "--json"]) == 0
    model = _snapshot(tmp_path / "out" / "architecture.json")
    invalid = Diagnostic(
        DiagnosticKind.CONTRACT_INVALID,
        "contract.json",
        "Target intent is invalid.",
        "Repair it.",
        code=DiagnosticCode.CONTRACT_INVALID,
    )

    result, _ = run_report(
        root,
        config=ScanConfig(("shop",), "shop", "architecture-contract.json", ""),
        analyzer=lambda *args, **kwargs: ObservationResult(model, model.coverage, (invalid,)),
    )

    assert result.exit_code == 2
    assert result.target is None
    assert invalid in result.diagnostics


def test_validate_on_a_contract_without_a_rule_says_no_rule_was_checked(tmp_path: Path) -> None:
    root = _zero_rule_repository(tmp_path / "repo")

    result, _ = run_validate(root, load_config(root), observe)

    assert (result.exit_code, result.declared_rules) == (0, "PASS")
    reason = next(
        row.reason for row in report_summary(result).verdicts if row.key == "declared_rules"
    )
    assert reason == "The contract is valid and declares no rule; no rule was checked."


def test_explore_reads_a_dart_package_through_the_init_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "dart"
    root.mkdir()
    for name in ("lib", "pubspec.yaml"):
        source = DART_FIXTURE_DIR / name
        target = root / name
        if source.is_dir():
            subprocess.run(["cp", "-R", str(source), str(target)], check=True)
        else:
            target.write_bytes(source.read_bytes())
    _repository(root, {})
    options = ["--language", "dart", "--source", "lib", "--namespace", "shop"]

    code, payload = _explore(
        capsys, "--root", str(root), "--output", str(tmp_path / "out"), *options
    )

    assert code == 0, payload["diagnostics"]
    assert (payload["target"], payload["scan_roots"]) == ("unavailable", ["lib"])
    assert architecture_report(_snapshot(tmp_path / "out" / "architecture.json")).memberships


def test_explore_reads_a_typescript_project_through_the_init_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = next(item for item in TYPESCRIPT_VARIANTS if item.id == "typescript-clean")
    root = typescript_repository(tmp_path, clean)
    options = ["--language", "typescript", "--source", "src", "--namespace", "shop"]

    code, payload = _explore(
        capsys,
        "--root",
        str(root),
        "--output",
        str(tmp_path / "out"),
        *options,
        "--tsconfig",
        "tsconfig.json",
    )

    assert code == 0, payload["diagnostics"]
    assert (payload["target"], payload["declared_rules"]) == ("unavailable", "UNKNOWN")
    assert architecture_report(_snapshot(tmp_path / "out" / "architecture.json")).memberships


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_explore_excludes_tests_but_keeps_production_and_marks_boundary_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], language: str
) -> None:
    files = {
        "src/shop/latest.py": (
            "from .test_support import value\n\ndef latest() -> int:\n    return value()\n"
        ),
        "src/shop/__init__.py": "",
        "src/shop/test_support.py": "def value() -> int:\n    return 1\n",
        "src/shop/tests/__init__.py": "",
        "src/shop/tests/test_inner.py": "def test_inner() -> None:\n    pass\n",
        "tests/test_outer.py": "def test_outer() -> None:\n    pass\n",
    }
    options = []
    excluded = {
        "src/shop/test_support.py",
        "src/shop/tests/test_inner.py",
        "tests/test_outer.py",
    }
    if language == "typescript":
        files = {
            "src/shop/latest.ts": (
                'import { value } from "./testSupport.test";\n'
                "export function latest(): number { return value(); }\n"
            ),
            "src/shop/testSupport.test.ts": "export function value(): number { return 1; }\n",
            "src/shop/__tests__/inner.test.ts": "export const testInner = 1;\n",
            "tests/outer.test.ts": "export const testOuter = 1;\n",
            "tsconfig.json": json.dumps({"include": ["src/**/*.ts", "tests/**/*.ts"]}),
        }
        options = [
            "--language",
            language,
            "--source",
            "src",
            "--namespace",
            "shop",
            "--tsconfig",
            "tsconfig.json",
        ]
        excluded = {
            "src/shop/testSupport.test.ts",
            "src/shop/__tests__/inner.test.ts",
            "tests/outer.test.ts",
        }
        production = "src/shop/latest.ts"
    else:
        files["pyproject.toml"] = '[project]\nname = "shop"\n'
        production = "src/shop/latest.py"
    root = _repository(tmp_path / "repo", files)

    code, payload = _explore(
        capsys, "--root", str(root), "--output", str(tmp_path / "out"), *options
    )

    assert code == 2, payload
    assert payload["observation_complete"] == "UNKNOWN"
    artifact = tmp_path / "out" / "architecture.json"
    assert artifact.exists(), json.dumps(payload["diagnostics"])
    model = _snapshot(artifact)
    observed = {item.data.get("file") for item in model.records("modules") or ()}
    assert production in observed
    assert not (excluded & observed)
    if language == "typescript":
        gaps = [
            item
            for item in model.coverage.failures
            if item.kind == "source_resolution_gap" and "testSupport.test.ts" in item.title
        ]
        assert len(gaps) == 1
        evidence = {item.id: item for item in model.evidence}
        assert any(evidence[item].file == production for item in gaps[0].evidence_ids)
        assert gaps[0].id in {item.id for item in model.records("unknowns") or ()}
    # A production import into excluded test code keeps the implementation scope incomplete.


@pytest.mark.parametrize(
    "import_statement",
    [
        "from .tests import helper as support",
        "from shop.tests import helper as support",
    ],
)
def test_explore_marks_imports_into_excluded_test_modules_unknown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    import_statement: str,
) -> None:
    root = _repository(
        tmp_path / "repo",
        {
            "pyproject.toml": '[project]\nname = "shop"\n',
            "src/shop/__init__.py": "",
            "src/shop/latest.py": (
                f"{import_statement}\n\ndef latest() -> int:\n    return support.value()\n"
            ),
            "src/shop/tests/helper.py": "def value() -> int:\n    return 1\n",
        },
    )

    code, payload = _explore(
        capsys,
        "--root",
        str(root),
        "--output",
        str(tmp_path / "out"),
        "--source",
        "src/shop",
        "--namespace",
        "shop",
    )

    assert code == 2, payload
    assert payload["observation_complete"] == "UNKNOWN"
    artifact = tmp_path / "out" / "architecture.json"
    assert artifact.exists(), json.dumps(payload["diagnostics"])
    model = _snapshot(artifact)
    production = next(
        item
        for item in model.records("modules") or ()
        if item.data.get("file") == "src/shop/latest.py"
    )
    gaps = [
        item
        for item in model.coverage.failures
        if item.data.get("resolution_dimension") == "imports"
    ]
    assert len(gaps) == 1
    assert gaps[0].data.get("source_module") == production.data.get("qualified_name")
    assert "excluded test source" in gaps[0].title
    assert gaps[0].evidence_ids
    assert gaps[0].id in {item.id for item in model.records("unknowns") or ()}


@pytest.mark.parametrize(
    ("import_statement", "test_path", "target_module"),
    [
        (
            "import tests.test_helper as support",
            "src/tests/test_helper.py",
            "tests.test_helper",
        ),
        (
            "from tests import helper as support",
            "src/tests/helper.py",
            "tests.helper",
        ),
    ],
)
def test_explore_keeps_unmapped_test_imports_unknown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    import_statement: str,
    test_path: str,
    target_module: str,
) -> None:
    root = _repository(
        tmp_path / "repo",
        {
            "pyproject.toml": '[project]\nname = "shop"\n',
            "src/shop/__init__.py": "",
            "src/shop/latest.py": (
                f"{import_statement}\n\ndef latest() -> int:\n    return support.value()\n"
            ),
            test_path: "def value() -> int:\n    return 1\n",
        },
    )

    code, payload = _explore(
        capsys,
        "--root",
        str(root),
        "--output",
        str(tmp_path / "out"),
        "--source",
        "src",
        "--namespace",
        "shop",
    )

    assert code == 2, payload
    assert payload["observation_complete"] == "UNKNOWN"
    artifact = tmp_path / "out" / "architecture.json"
    assert artifact.exists(), json.dumps(payload["diagnostics"])
    model = _snapshot(artifact)
    gaps = [
        item
        for item in model.coverage.failures
        if item.data.get("resolution_dimension") == "imports"
    ]
    assert len(gaps) == 1
    assert target_module in gaps[0].title
    assert gaps[0].evidence_ids


@pytest.mark.parametrize(
    ("language", "alias_kind"),
    [
        ("python", "file"),
        ("python", "directory"),
        ("typescript", "file"),
        ("typescript", "directory"),
    ],
)
def test_explore_symlink_alias_to_test_source_stays_unknown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    language: str,
    alias_kind: str,
) -> None:
    if language == "python" and alias_kind == "file":
        files = {
            "pyproject.toml": '[project]\nname = "shop"\n',
            "src/shop/__init__.py": "",
            "src/shop/app.py": "from shop.latest import value\n\nvalue()\n",
            "src/shop/tests/test_latest.py": "def value() -> int:\n    return 1\n",
        }
        link, target, alias = (
            "src/shop/latest.py",
            "src/shop/tests/test_latest.py",
            "src/shop/latest.py",
        )
    elif language == "python":
        files = {
            "pyproject.toml": '[project]\nname = "shop"\n',
            "src/shop/__init__.py": "",
            "src/shop/app.py": "from shop.latest.helper import value\n\nvalue()\n",
            "src/shop/tests/__init__.py": "",
            "src/shop/tests/helper.py": "def value() -> int:\n    return 1\n",
        }
        link, target, alias = (
            "src/shop/latest",
            "src/shop/tests",
            "src/shop/latest/helper.py",
        )
    elif alias_kind == "file":
        files = {
            "src/shop/app.ts": 'import { value } from "./latest";\nvalue();\n',
            "src/shop/tests/latest.test.ts": "export function value(): number { return 1; }\n",
            "tsconfig.json": json.dumps({"include": ["src/**/*.ts"]}),
        }
        link, target, alias = (
            "src/shop/latest.ts",
            "src/shop/tests/latest.test.ts",
            "src/shop/latest.ts",
        )
    else:
        files = {
            "src/shop/app.ts": 'import { value } from "./latest/helper";\nvalue();\n',
            "src/shop/tests/helper.ts": "export function value(): number { return 1; }\n",
            "tsconfig.json": json.dumps({"include": ["src/**/*.ts"]}),
        }
        link, target, alias = (
            "src/shop/latest",
            "src/shop/tests",
            "src/shop/latest/helper.ts",
        )
    root = _repository_with_symlink(tmp_path / "repo", files, link, target)
    options = (
        [
            "--language",
            "typescript",
            "--source",
            "src",
            "--namespace",
            "shop",
            "--tsconfig",
            "tsconfig.json",
        ]
        if language == "typescript"
        else ["--source", "src", "--namespace", "shop"]
    )

    code, payload = _explore(
        capsys,
        "--root",
        str(root),
        "--output",
        str(tmp_path / "out"),
        *options,
    )

    assert code == 2, payload
    assert payload["observation_complete"] == "UNKNOWN"
    artifact = tmp_path / "out" / "architecture.json"
    assert artifact.exists(), json.dumps(payload["diagnostics"])
    model = _snapshot(artifact)
    observed = {item.data.get("file") for item in model.records("modules") or ()}
    assert alias not in observed
    gaps = [item for item in model.coverage.failures if "excluded test source" in item.title]
    assert len(gaps) == 1
    evidence = {item.id: item for item in model.evidence}
    suffix = "ts" if language == "typescript" else "py"
    assert any(evidence[item].file.endswith(f"app.{suffix}") for item in gaps[0].evidence_ids)
    assert gaps[0].id in {item.id for item in model.records("unknowns") or ()}


@pytest.mark.parametrize("alias_kind", ["file", "directory"])
def test_explore_symlink_to_test_outside_source_root_stays_unknown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    alias_kind: str,
) -> None:
    if alias_kind == "file":
        files = {
            "pyproject.toml": '[project]\nname = "shop"\n',
            "src/shop/__init__.py": "",
            "src/shop/app.py": "from shop.latest import value\n\nvalue()\n",
            "tests/test_latest.py": "def value() -> int:\n    return 1\n",
        }
        link, target, alias = (
            "src/shop/latest.py",
            "tests/test_latest.py",
            "src/shop/latest.py",
        )
    else:
        files = {
            "pyproject.toml": '[project]\nname = "shop"\n',
            "src/shop/__init__.py": "",
            "src/shop/app.py": "from shop.latest.helper import value\n\nvalue()\n",
            "tests/helper.py": "def value() -> int:\n    return 1\n",
        }
        link, target, alias = "src/shop/latest", "tests", "src/shop/latest/helper.py"
    root = _repository_with_symlink(tmp_path / "repo", files, link, target)

    code, payload = _explore(
        capsys,
        "--root",
        str(root),
        "--output",
        str(tmp_path / "out"),
        "--source",
        "src/shop",
        "--namespace",
        "shop",
    )

    assert code == 2, payload
    assert payload["observation_complete"] == "UNKNOWN"
    artifact = tmp_path / "out" / "architecture.json"
    assert artifact.exists(), json.dumps(payload["diagnostics"])
    model = _snapshot(artifact)
    observed = {item.data.get("file") for item in model.records("modules") or ()}
    assert alias not in observed
    gaps = [item for item in model.coverage.failures if "excluded test source" in item.title]
    assert len(gaps) == 1
    evidence = {item.id: item for item in model.evidence}
    assert any(evidence[item].file == "src/shop/app.py" for item in gaps[0].evidence_ids)
    assert gaps[0].id in {item.id for item in model.records("unknowns") or ()}


def test_explore_accepts_a_finite_collector_output_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = next(item for item in TYPESCRIPT_VARIANTS if item.id == "typescript-clean")
    root = typescript_repository(tmp_path, clean)
    options = ["--language", "typescript", "--source", "src", "--namespace", "shop"]
    common = ["--root", str(root), "--output", str(tmp_path / "out"), *options]

    assert (
        main(
            [
                "explore",
                *common,
                "--tsconfig",
                "tsconfig.json",
                "--json",
                "--collector-output-limit-bytes",
                "1",
            ]
        )
        == 2
    )
    limited = json.loads(capsys.readouterr().out)
    assert "1 byte limit" in limited["diagnostics"][0]["unknown_claim"]
    assert "--collector-output-limit-bytes" in limited["diagnostics"][0]["unknown_claim"]
    assert "[scan]" not in limited["diagnostics"][0]["unknown_claim"]

    assert (
        main(
            [
                "explore",
                *common,
                "--tsconfig",
                "tsconfig.json",
                "--json",
                "--collector-output-limit-bytes",
                str(16 * 1024 * 1024),
            ]
        )
        == 0
    )
    complete = json.loads(capsys.readouterr().out)
    assert complete["observation_complete"] == "PASS"


def test_explore_keeps_its_findings_one_click_away(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cyclic = {
        **_SOURCES,
        "shop/store/repository.py": "import shop.app.orders\n\n\ndef save(value: int) -> int:\n"
        "    return value\n",
    }
    root = _repository(tmp_path / "repo", cyclic)

    code, payload = _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))

    assert code == 0, payload["diagnostics"]
    assert payload["findings"]
    page = (tmp_path / "out" / "architecture.report.html").read_text()
    # AD-285: closed findings keep the Explorer on an 800x600 first screen.
    assert '<details class="atlas-findings"><summary><h2 id="findings-heading"' in page


def test_explore_opens_a_large_component_level_by_level(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = {
        path.relative_to(EXPLORE_FIXTURE_DIR).as_posix(): path.read_text()
        for path in EXPLORE_FIXTURE_DIR.rglob("*")
        if path.is_file()
    }
    root = _repository(tmp_path / "repo", {**fixture, **nested_engine_files()})
    output = tmp_path / "out"
    assert _explore(capsys, "--root", str(root), "--output", str(output))[0] == 0
    snapshot = str(output / "architecture.json")

    assert main(["report", "--input", snapshot, "--only", "architecture", "--json"]) == 0
    components = json.loads(capsys.readouterr().out)["architecture_projection"]["components"]
    query = ["report", "--input", snapshot, "--only", "architecture"]
    leaf = main([*query, "--component", "engine:io:clients:COMP-RDBMS", "--json"])

    parents = {item["id"]: item.get("parent_id") for item in components}
    assert sorted(key for key, parent in parents.items() if parent is None) == [
        "COMP-APP",
        "COMP-CLI",
        "COMP-ENGINE",
        "COMP-STORE",
    ]
    chain, node = [], "engine:io:clients:COMP-RDBMS"
    while node is not None:
        chain.append(node)
        node = parents[node]
    assert chain == [
        "engine:io:clients:COMP-RDBMS",
        "engine:io:COMP-CLIENTS",
        "engine:COMP-IO",
        "COMP-ENGINE",
    ]
    page = (output / "architecture.report.html").read_text()
    assert "4 top-level components (9 with all levels)" in page
    # 20 modules stay one leaf; the 5-module core is not split.
    assert {"engine:io:clients:COMP-MONGO", "engine:COMP-CORE"} <= parents.keys()
    assert leaf == 0


def test_an_undeclared_python_range_is_a_coverage_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sources = {**_SOURCES, "pyproject.toml": '[project]\nname = "shop"\n'}
    root = _repository(tmp_path / "repo", sources)

    code, payload = _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))

    assert code == 0, payload["diagnostics"]
    assert payload["observation_complete"] == "PASS"
    assert [item["kind"] for item in payload["notes"]] == ["runtime_mismatch"]
    page = (tmp_path / "out" / "architecture.report.html").read_text()
    assert "Coverage note: The supported Python range is not declared." in page


def test_a_python_outside_the_declared_range_still_blocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sources = {
        **_SOURCES,
        "pyproject.toml": '[project]\nname = "shop"\nrequires-python = ">=3.99"\n',
    }
    root = _repository(tmp_path / "repo", sources)

    code, payload = _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))

    assert code == 2
    assert [item["kind"] for item in payload["diagnostics"]] == ["runtime_mismatch"]
    assert "notes" not in payload


def test_explore_shows_no_deviation_without_a_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo", {**_SOURCES, **nested_engine_files()})

    assert _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))[0] == 0

    page = (tmp_path / "out" / "architecture.report.html").read_text()
    payload = json.loads(re.search(r'id="flow-data"[^>]*>(.*?)</script>', page, re.S)[1])
    # AD-285: an observed crossing deviates from nothing when nothing is declared.
    assert payload["atlas"]["deviations"] == []
    assert all(not level["deviation_ids"] for level in payload["atlas"]["levels"])


def test_explore_leaves_the_git_index_of_a_read_only_snapshot_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo")
    # A new mtime with the same bytes makes a plain `git status` rewrite its index cache.
    source = root / "shop/store/repository.py"
    source.write_text(source.read_text())
    os.utime(source, (1, 1))
    index = (root / ".git/index").read_bytes()

    assert _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))[0] == 0
    assert (root / ".git/index").read_bytes() == index
    paths = [root / ".git", *(root / ".git").rglob("*")]
    for path in paths:
        path.chmod(path.stat().st_mode & ~0o222)
    try:
        code, payload = _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))
    finally:
        for path in paths:
            path.chmod(path.stat().st_mode | 0o200)

    assert code == 0, payload["diagnostics"]
    assert (root / ".git/index").read_bytes() == index


@pytest.mark.parametrize("requires", ["", 'requires-python = ">=3.11"\n'])
def test_a_source_failure_still_blocks_with_or_without_a_python_range(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], requires: str
) -> None:
    sources = {
        **_SOURCES,
        "pyproject.toml": f'[project]\nname = "shop"\n{requires}',
        "shop/app/broken.py": "def broken(:\n    pass\n",
    }
    root = _repository(tmp_path / "repo", sources)

    code, payload = _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))

    # AD-285: the note never hides a source failure; the result names the failing file.
    assert code == 2
    assert payload["diagnostics"]
    assert "notes" not in payload
    assert "shop/app/broken.py" in json.dumps(payload["coverage"]["failures"])


def test_a_public_list_without_a_rule_is_a_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # AD-285: a declared interface is something to check the code against.
    root = _zero_rule_repository(tmp_path / "repo", public=["shop.store.repository:save"])

    code = main(["report", "--root", str(root), "--output", str(tmp_path / "a.json"), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert "target" not in payload
    page = (tmp_path / "a.report.html").read_text()
    assert "Target unavailable" not in page.split('id="flow-data"')[0]


def test_a_view_check_does_not_call_a_layout_group_declared(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "repo")
    snapshot = tmp_path / "out" / "architecture.json"
    assert _explore(capsys, "--root", str(root), "--output", str(snapshot.parent))[0] == 0
    raw = json.loads(snapshot.read_bytes())
    spec = {
        "schema_version": "1.0.0",
        "title": "Layout",
        "snapshot": {
            "source_digest": raw["source"]["source_digest"],
            "contract_digest": raw["contract"]["digest"],
        },
        "nodes": ["COMP-APP", "COMP-STORE"],
        "edges": [{"source": "COMP-APP", "target": "COMP-STORE", "kind": "requires"}],
    }
    (tmp_path / "view.json").write_text(json.dumps(spec))

    main(["view", "check", str(tmp_path / "view.json"), "--snapshot", str(snapshot), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert {item["status"] for item in result["nodes"]} == {"unknown"}
    assert [item["status"] for item in result["edges"]] == ["unknown"]


def test_explore_deletes_only_its_own_files_in_the_output_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "out"
    output.mkdir()
    for name in ("architecture.notes.html", "architecture.detail-component-0123456789abcdef.html"):
        (output / name).write_text("kept?")
    empty = _repository(tmp_path / "empty", {})
    root = _repository(tmp_path / "repo")

    assert _explore(capsys, "--root", str(empty), "--output", str(output))[0] == 2
    assert (output / "architecture.notes.html").exists()
    assert _explore(capsys, "--root", str(root), "--output", str(output))[0] == 0

    assert (output / "architecture.notes.html").read_text() == "kept?"
    assert not (output / "architecture.detail-component-0123456789abcdef.html").exists()


def test_the_terminal_names_the_explore_command() -> None:
    console = Console(record=True, width=120)
    result = RunResult(Command.REPORT, 0, root_name="repo", root_digest="0" * 16)

    print_result(result, report_summary(result), artifacts=(), console=console)

    assert "archkeel explore" in console.export_text()


def test_a_violation_keeps_its_fail_without_a_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # AD-285: only a vacuous PASS loses its verdict; an observed violation stays FAIL.
    root = _zero_rule_repository(
        tmp_path / "repo", packages=["shop.app", "shop.store"], namespace="shop.app"
    )

    code = main(["report", "--root", str(root), "--output", str(tmp_path / "a.json"), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert payload["declared_rules"] == "FAIL"
    assert "target" not in payload
    page = (tmp_path / "a.report.html").read_text()
    assert "no rule passes or fails" not in page


def test_an_empty_public_list_is_a_declared_interface(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # AD-285: `public: []` declares no public surface; that is an interface decision.
    root = _zero_rule_repository(tmp_path / "repo", public=[])

    code = main(["report", "--root", str(root), "--output", str(tmp_path / "a.json"), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert "target" not in payload


@pytest.mark.browser
def test_an_explore_card_shows_its_label_and_no_placeholder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # AD-288: the layout declares no responsibility, so a card shows only its label.
    api = pytest.importorskip("playwright.sync_api")
    from browser_report_support import _browser_page

    root = _repository(tmp_path / "repo")
    assert _explore(capsys, "--root", str(root), "--output", str(tmp_path / "out"))[0] == 0
    html = (tmp_path / "out" / "architecture.report.html").read_text()
    playwright, browser, page = _browser_page(api, html, width=800, height=600)
    try:
        card = page.locator('.flow-nodes [data-uml-id="COMP-STORE"]')
        card.wait_for()
        assert (card.locator(".label").text_content(), card.locator(".meta").text_content()) == (
            "store",
            "",
        )
        assert "Not declared" not in page.locator(".flow-nodes").text_content()
    finally:
        browser.close()
        playwright.stop()
