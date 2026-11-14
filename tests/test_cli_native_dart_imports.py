# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-468: Dart import rules through the release core and the default shell."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_cli_core_only_scan import command
from test_cli_native_python_imports import RULE, component, rows, verdict

PUBSPEC = "name: shop\nenvironment:\n  sdk: ^3.4.0\n"
BASE = {
    "pubspec.yaml": PUBSPEC,
    "lib/domain/model.dart": "class Model {}\n",
    "lib/data/repo.dart": "import 'package:shop/domain/model.dart';\n",
}
RULES = ["FORBID", "ASSIGN", "CYCLES", "REQUIRES"]


def contract_rules() -> list[dict[str, Any]]:
    return [
        {
            **RULE,
            "id": "FORBID",
            "kind": "forbidden_dependency",
            "source": "shop.domain",
            "target": "shop.data",
            "include_type_checking": True,
        },
        {**RULE, "id": "ASSIGN", "kind": "complete_assignment", "source": "shop"},
        {**RULE, "id": "CYCLES", "kind": "no_component_cycles"},
        {**RULE, "id": "REQUIRES", "kind": "complete_requires"},
    ]


def project(root: Path, files: dict[str, str | bytes], *, extra: str = "") -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode() if isinstance(text, str) else text)
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "dart"\nroots = ["lib"]\nnamespace = "shop"\n'
        f'contract = "architecture-contract.json"\n{extra}'
    )
    contract = {
        "schema_version": "2.2.0",
        "components": [
            component("domain", ["shop.domain"]),
            component("data", ["shop.data"], ["domain"]),
        ],
        "rules": contract_rules(),
    }
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    _commit(root)
    return root


def _commit(root: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)


def all_unknown(result: dict[str, Any]) -> None:
    assert rows(result) == dict.fromkeys(RULES, "UNKNOWN"), result["frame"]["explained"]
    assert result["status"] == "UNKNOWN" and result["exit_code"] == 2


@pytest.mark.parametrize("verb", ["validate", "report"])
def test_a_clean_dart_project_passes_each_import_rule(
    release_core: Path, tmp_path: Path, verb: str
) -> None:
    result = verdict(release_core, project(tmp_path, BASE), verb)
    assert rows(result) == dict.fromkeys(RULES, "PASS"), result["frame"]["explained"]
    assert result["status"] == "PASS" and result["exit_code"] == 0


def test_a_forbidden_dart_import_fails_with_its_file(release_core: Path, tmp_path: Path) -> None:
    files = {**BASE, "lib/domain/model.dart": "import '../data/repo.dart';\nclass Model {}\n"}
    result = verdict(release_core, project(tmp_path, files))
    assert rows(result)["FORBID"] == "FAIL"
    assert rows(result)["CYCLES"] == "FAIL"
    assert "lib/domain/model.dart" in json.dumps(result["frame"]["violations"]) + json.dumps(
        result["frame"]["locations"]
    )


def test_a_part_in_the_component_of_its_library_passes(release_core: Path, tmp_path: Path) -> None:
    files = {
        **BASE,
        "lib/data/repo.dart": "import 'package:shop/domain/model.dart';\npart 'repo_part.dart';\n",
        "lib/data/repo_part.dart": "part of 'repo.dart';\n",
    }
    result = verdict(release_core, project(tmp_path, files))
    assert rows(result) == dict.fromkeys(RULES, "PASS"), result["frame"]["explained"]


def test_a_part_in_another_component_makes_each_rule_unknown(
    release_core: Path, tmp_path: Path
) -> None:
    files = {
        **BASE,
        "lib/data/repo.dart": "import 'package:shop/domain/model.dart';\n"
        "part '../domain/repo_part.dart';\n",
        "lib/domain/repo_part.dart": "part of '../data/repo.dart';\n",
    }
    result = verdict(release_core, project(tmp_path, files))
    all_unknown(result)
    assert "lib/domain/repo_part.dart belongs to a module of another component" in json.dumps(
        result["frame"]
    )


DENSE = "var x = [" + "1," * 70_000 + "];\n"
GAPS: dict[str, dict[str, str]] = {
    "DartTargetMissing": {"lib/data/x.dart": "import 'gone.dart';\n"},
    "DartTargetNotSelected": {
        "lib/data/x.dart": "import '../../tool/t.dart';\n",
        "tool/t.dart": "",
    },
    "DartTargetOutside": {"lib/data/x.dart": "import '../../../x.dart';\n"},
    "DartTargetIsPart": {
        "lib/data/x.dart": "part 'p.dart';\n",
        "lib/data/p.dart": "part of 'x.dart';\n",
        "lib/data/y.dart": "import 'p.dart';\n",
    },
    "DartTargetUnparsed": {"lib/data/x.dart": "class {", "lib/data/y.dart": "import 'x.dart';\n"},
    "DartUnsupportedUri": {"lib/data/x.dart": "import 'http://x/a.dart';\n"},
    "DartUriNotLiteral": {"lib/data/x.dart": "import '$a.dart';\nconst a = 'b';\n"},
    "DartMirrors": {"lib/data/x.dart": "import 'dart:mirrors';\n"},
    "DartIsolate": {"lib/data/x.dart": "import 'dart:isolate';\n"},
    "DartPartUnowned": {"lib/data/p.dart": "part of 'repo.dart';\n"},
    "DartPartNotPart": {"lib/data/x.dart": "part 'y.dart';\n", "lib/data/y.dart": ""},
    "DartPartConflict": {
        "lib/data/x.dart": "part 'p.dart';\n",
        "lib/data/y.dart": "part 'p.dart';\n",
        "lib/data/p.dart": "part of 'x.dart';\n",
    },
    "DartWorkspace": {"pubspec.yaml": PUBSPEC + "resolution: workspace\n"},
    "DartPathDependency": {"pubspec.yaml": PUBSPEC + "dependencies:\n  core:\n    path: ../core\n"},
    "DartNestedPackage": {"lib/data/inner/pubspec.yaml": "name: inner\n"},
    "DartPackageConfig": {"package_config.json": "{}"},
    "DartParseBudget": {"lib/data/x.dart": DENSE},
}


@pytest.mark.parametrize("name", sorted(GAPS))
def test_each_survey_gap_makes_each_rule_unknown(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    result = verdict(release_core, project(tmp_path, {**BASE, **GAPS[name]}))
    all_unknown(result)
    assert name in json.dumps(result["frame"]["collection_gaps"]), result["frame"]["scope"]


def test_the_gap_plants_cover_each_survey_gap_name() -> None:
    record = Path(__file__).parents[1] / "docs/architecture/decisions"
    text = next(record.glob("ad-454-*.md")).read_text()
    named = {line.split("`")[1] for line in text.splitlines() if line.startswith("| `Dart")}
    assert named == set(GAPS)


def test_a_dart_test_exclusion_is_refused_by_name(release_core: Path, tmp_path: Path) -> None:
    root = project(tmp_path, BASE, extra="exclude_test_sources = true\n")
    done = command(release_core, root, "--json")
    result = json.loads(done.stdout)
    assert result["exit_code"] == 2
    assert "exclude_test_sources is not supported for a Dart project" in json.dumps(result)


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need privileges on Windows")
def test_a_linked_directory_below_a_scan_root_makes_each_rule_unknown(
    release_core: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    (outside / "lib").mkdir(parents=True)
    (outside / "lib" / "hidden.dart").write_text("import 'package:shop/data/repo.dart';\n")
    root = tmp_path / "project"
    root.mkdir()
    (root / "lib" / "domain").mkdir(parents=True)
    (root / "lib" / "domain" / "linked").symlink_to(outside / "lib", target_is_directory=True)
    result = verdict(release_core, project(root, BASE))
    all_unknown(result)
    assert "source directory is a symlink" in json.dumps(result["frame"]["collection_gaps"])


def test_a_component_outside_the_namespace_makes_each_rule_unknown(
    release_core: Path, tmp_path: Path
) -> None:
    root = project(tmp_path, BASE)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["components"].append(component("other", ["other.pkg"]))
    path.write_text(json.dumps(contract))
    _commit_change(root)
    result = verdict(release_core, root)
    assert set(rows(result).values()) <= {"UNKNOWN"}, rows(result)
    assert "outside the namespace" in json.dumps(result["frame"])


def _commit_change(root: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for step in (["add", "-A"], ["commit", "-qm", "change"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)
