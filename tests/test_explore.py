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

    # A production import into excluded test code keeps the implementation scope incomplete.


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
