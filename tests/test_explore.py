# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-285: `archkeel explore` shows the as-is code of a repository that has no contract."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from rich.console import Console

from archkeel.cli import main
from archkeel.ir.codec import (
    decode_canonical_model,
    decode_json,
    parse_observation,
)
from archkeel.ir.model import Command, RunResult
from archkeel.ir.report_graph import architecture_report
from archkeel.render.summary import report_summary
from archkeel.render.terminal import print_result
from fixtures.architecture_demo import replay
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
    "import_statement",
    ["import shop.tests", "from shop import tests"],
)
def test_explore_keeps_namespace_test_package_import_unknown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    import_statement: str,
) -> None:
    root = _repository(
        tmp_path / "repo",
        {
            "pyproject.toml": '[project]\nname = "shop"\n',
            "src/shop/__init__.py": "",
            "src/shop/app.py": f"{import_statement}\n",
            "src/shop/tests/test_helper.py": "def helper() -> int:\n    return 1\n",
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
    gaps = [
        item
        for item in model.coverage.failures
        if item.data.get("resolution_dimension") == "imports"
    ]
    assert len(gaps) == 1
    assert "shop.tests" in gaps[0].title
    evidence = {item.id: item for item in model.evidence}
    assert any(evidence[item].file == "src/shop/app.py" for item in gaps[0].evidence_ids)
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
    "statement",
    [
        'import importlib\nimportlib.import_module("shop.tests.helper")',
        'import importlib\n__import__("shop.tests.helper")',
    ],
)
def test_explore_keeps_dynamic_imports_of_excluded_tests_unknown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    statement: str,
) -> None:
    root = _repository(
        tmp_path / "repo",
        {
            "pyproject.toml": '[project]\nname = "shop"\n',
            "src/shop/__init__.py": "",
            "src/shop/app.py": f"{statement}\n",
            "src/shop/tests/helper.py": "value = 1\n",
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
    model = _snapshot(tmp_path / "out" / "architecture.json")
    gaps = [item for item in model.coverage.failures if "excluded test source" in item.title]
    assert len(gaps) == 1
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


def test_the_terminal_names_the_explore_command() -> None:
    console = Console(record=True, width=120)
    result = RunResult(Command.REPORT, 0, root_name="repo", root_digest="0" * 16)

    print_result(result, report_summary(result), artifacts=(), console=console)

    assert "archkeel explore" in console.export_text()


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
