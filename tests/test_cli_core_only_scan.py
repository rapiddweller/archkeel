# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Real scan requests through the product entry, with the Python decision packages blocked."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from core_support import HONEST, SUFFIX, case_root
from rust_repository import repository
from test_cli_core_only import GUARD, ROOT


def command(
    binary: Path,
    root: Path | None,
    *flags: str,
    cwd: Path | None = None,
    verb: str = "validate",
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
            verb,
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


@pytest.mark.parametrize(
    "verb,form",
    [
        ("validate", "--text"),
        ("validate", "--json"),
        ("report", "--text"),
        ("report", "--json"),
        ("validate", "--core-only"),
        ("report", "--core-only"),
        ("check", "--json"),
    ],
)
def test_a_real_pass_has_no_python_collector_ir_or_checker(
    built: Path, verb: str, form: str
) -> None:
    with case_root(HONEST) as root:
        done = command(built / f"archkeel-core{SUFFIX}", root, form, verb=verb)
    assert done.returncode == (2 if verb == "check" else 0), done.stdout + done.stderr
    assert "Traceback" not in done.stderr
    assert "#1103" in done.stdout if verb == "check" else "PASS" in done.stdout


def test_a_real_rust_pass_also_blocks_python_decision_imports(built: Path, tmp_path: Path) -> None:
    binary = built / f"archkeel-core{SUFFIX}"
    root = repository(tmp_path / "project", binary)
    done = command(binary, root, "--json")
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


def test_an_unknown_source_gap_names_its_collector_cause_and_file(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "src/b/t.ts").write_text("export type T = ;\n")
        done = command(built / f"archkeel-core{SUFFIX}", root, "--text")
    assert done.returncode == 2, done.stdout + done.stderr
    assert "src/b/t.ts" in done.stdout
    assert "Source gap" in done.stdout and "Action:" in done.stdout


def test_a_construct_failure_from_main_keeps_its_cause_and_location(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "src/a/a.ts").write_text('export function a(x: string) { return x === "a"; }\n')
        path = root / "architecture-contract.json"
        contract = json.loads(path.read_text())
        contract["rules"].append(
            {
                "id": "NO-RAW-CONTROL",
                "kind": "forbidden_construct",
                "source": "app",
                "constructs": ["string_literal_compare"],
                "rationale": "Use typed control.",
                "provenance": ["README.md"],
                "decided_by": "architect",
            }
        )
        path.write_text(json.dumps(contract))
        done = command(built / f"archkeel-core{SUFFIX}", root, "--text")
    assert done.returncode == 1, done.stdout + done.stderr
    for text in ("NO-RAW-CONTROL", "forbidden construct", "string_literal_compare", "src/a/a.ts:1"):
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
        # AD-458: each ordered component pair is decided, so no hygiene row hides the gap.
        allowed = [
            {
                **contract["rules"][0],
                "id": f"ALLOW-{source}",
                "kind": "allowed_dependency",
                "source": f"app.src.{source}",
                "target": f"app.src.{target}",
            }
            for source, target in (("a", "b"), ("b", "a"))
        ]
        contract["rules"] = allowed if declaration else []
        if not declaration:
            contract["components"] = contract["components"][:1]
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
        assert snapshot["dirty"] is True


def test_an_explicit_project_outside_any_repository_refuses(built: Path, tmp_path: Path) -> None:
    project = tmp_path / "project"
    with case_root(HONEST) as root:
        shutil.copytree(root, project, ignore=shutil.ignore_patterns(".git"))
    done = command(built / f"archkeel-core{SUFFIX}", project, "--json")
    assert done.returncode == 2, done.stdout + done.stderr
    assert "git head" in done.stdout and "is in no Git repository" in done.stdout


def test_an_unreadable_config_names_no_contract_parse_gap(built: Path) -> None:
    with case_root(HONEST) as root:
        done = command(built / f"archkeel-core{SUFFIX}", root, "--config", "missing.toml", "--json")
    assert done.returncode == 2, done.stdout + done.stderr
    assert "cannot read missing.toml" in done.stdout
    assert "invalid contract" not in done.stdout
    assert "refused" not in json.loads(done.stdout)["frame"]["self_test"]["contract"]
