# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Real scan requests through the product entry, with both Python decision packages blocked."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_cli_core_only import GUARD, ROOT
from test_cli_native_core_scan import HONEST, SUFFIX, _rust_repository, built, case_root

__all__ = ["built"]


def command(
    binary: Path,
    root: Path | None,
    *flags: str,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    guard = GUARD.replace(
        "from archkeel.cli import main",
        "from pathlib import Path\nfrom archkeel.cli import core_only\n"
        f"core_only.locate_core = lambda: Path({str(binary)!r})\nfrom archkeel.cli import main",
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            guard,
            "validate",
            "--core-only",
            *([] if root is None else ["--root", str(root)]),
            *flags,
        ],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        cwd=cwd,
    )


def test_a_real_pass_has_no_python_collector_ir_or_checker(built: Path) -> None:
    with case_root(HONEST) as root:
        done = command(built / f"archkeel-core{SUFFIX}", root, "--json")
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads(done.stdout)["status"] == "PASS"


def test_a_real_rust_pass_also_blocks_python_decision_imports(built: Path, tmp_path: Path) -> None:
    root = _rust_repository(built, tmp_path)
    done = command(built / f"archkeel-core{SUFFIX}", root, "--json")
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads(done.stdout)["status"] == "PASS"


def test_a_real_failure_names_its_edge_and_source_location(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "src/a/a.ts").write_text(
            'import type { T } from "../b/t";\nexport const a: T = 1;\n'
        )
        done = command(built / f"archkeel-core{SUFFIX}", root, "--text")
    assert done.returncode == 1, done.stdout + done.stderr
    for text in ("REQUIRES", "app.src.a.a_x2e_ts -> app.src.b.t_x2e_ts", "src/a/a.ts:1", "Action:"):
        assert text in done.stdout


@pytest.mark.parametrize("language", ["python", "dart"])
def test_an_unsupported_profile_refuses_by_name(built: Path, language: str) -> None:
    with case_root(HONEST) as root:
        (root / "archkeel.toml").write_text(
            f'[scan]\nlanguage = "{language}"\nroots = ["src"]\n'
            'namespace = "app"\ncontract = "architecture-contract.json"\n'
        )
        done = command(built / f"archkeel-core{SUFFIX}", root, "--json")
    assert done.returncode == 2, done.stdout + done.stderr
    result = json.loads(done.stdout)
    assert "profile" in done.stdout and language in done.stdout
    assert "refused" not in result["frame"]["self_test"]["contract"]


@pytest.mark.parametrize("declaration", [False, True])
def test_zero_decided_rules_stay_unknown_and_nonzero(built: Path, declaration: bool) -> None:
    with case_root(HONEST) as root:
        path = root / "architecture-contract.json"
        contract = json.loads(path.read_text())
        contract["rules"] = (
            [
                {
                    **contract["rules"][0],
                    "id": "ALLOW",
                    "kind": "allowed_dependency",
                    "source": "a",
                    "target": "b",
                }
            ]
            if declaration
            else []
        )
        path.write_text(json.dumps(contract))
        done = command(built / f"archkeel-core{SUFFIX}", root, "--json")
    assert done.returncode == 2, done.stdout + done.stderr
    assert "no decided rule" in done.stdout
    result = json.loads(done.stdout)
    assert result["status"] == "UNKNOWN"
    assert any(gap["kind"] == "no_decided_rule" for gap in result["gaps"])


def test_an_inside_contract_is_refused_by_its_path(built: Path) -> None:
    with case_root(HONEST) as root:
        path = root / "architecture-contract.json"
        contract = json.loads(path.read_text())
        contract["components"][0]["inside"] = "inside.json"
        path.write_text(json.dumps(contract))
        done = command(built / f"archkeel-core{SUFFIX}", root, "--json")
    assert done.returncode == 2, done.stdout + done.stderr
    assert "inside contracts" in done.stdout and "inside.json" in done.stdout


def test_subdirectory_and_selected_config_use_the_repository_root(built: Path) -> None:
    with case_root(HONEST) as root:
        config = root / "selected.toml"
        config.write_bytes((root / "archkeel.toml").read_bytes())
        nested = root / "subdirectory"
        nested.mkdir()
        done = command(
            built / f"archkeel-core{SUFFIX}", None, "--config", config.name, "--json", cwd=nested
        )
        assert done.returncode == 0, done.stdout + done.stderr
        derived = json.loads(done.stdout)["frame"]["self_test"]["collect"]["request"]
        assert derived["snapshot"]["root"] == str(root)
        assert derived["snapshot"]["dirty"] is True


def test_an_explicit_project_root_inside_a_repository_keeps_its_own_config(built: Path) -> None:
    with case_root(HONEST) as root:
        project = root / "project"
        project.mkdir()
        for name in (
            "src",
            "archkeel.toml",
            "tsconfig.json",
            "architecture-contract.json",
            "README.md",
        ):
            source = root / name
            if source.is_dir():
                shutil.copytree(source, project / name)
            else:
                shutil.copy2(source, project / name)
        done = command(built / f"archkeel-core{SUFFIX}", project, "--json")
        assert done.returncode == 0, done.stdout + done.stderr
        snapshot = json.loads(done.stdout)["frame"]["self_test"]["collect"]["request"]["snapshot"]
        assert snapshot["root"] == str(project)


def test_an_unreadable_config_names_no_contract_parse_gap(built: Path) -> None:
    with case_root(HONEST) as root:
        done = command(built / f"archkeel-core{SUFFIX}", root, "--config", "missing.toml", "--json")
    assert done.returncode == 2, done.stdout + done.stderr
    assert "cannot read missing.toml" in done.stdout
    assert "invalid contract" not in done.stdout
    assert "refused" not in json.loads(done.stdout)["frame"]["self_test"]["contract"]
