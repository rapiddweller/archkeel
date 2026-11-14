# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Python import verdicts use the release core and the default shell."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def release() -> Path:
    subprocess.run(
        ["cargo", "build", "--locked", "--release", "-q", "-p", "archkeel-core"],
        cwd=ROOT / "native",
        env={**os.environ, "ARCHKEEL_VERSION": "0.0.0"},
        check=True,
    )
    return ROOT / "native/target/release/archkeel-core"


def project(root: Path, source: str = "") -> None:
    package = root / "src/app"
    package.mkdir(parents=True)
    for name, text in {"__init__.py": "", "client.py": source, "service.py": "VALUE = 1\n"}.items():
        (package / name).write_text(text)
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "python"\nroots = ["src"]\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\n'
    )
    component = {
        "role": "component", "responsibilities": ["Own the module."],
        "forbidden_responsibilities": ["Own other modules."], "provenance": ["p"],
        "decided_by": "architect",
    }
    rule = {"rationale": "Keep the dependency absent.", "provenance": ["p"], "decided_by": "architect"}
    (root / "architecture-contract.json").write_text(json.dumps({
        "schema_version": "3.14.0",
        "components": [
            {**component, "id": "COMP-CLIENT", "label": "client", "exact_modules": ["app", "app.client"]},
            {**component, "id": "COMP-SERVICE", "label": "service", "exact_modules": ["app.service"]},
        ],
        "rules": [{**rule, "id": "FORBID", "kind": "forbidden_dependency", "source": "app.client", "target": "app.service"}],
    }))
    subprocess.run(["git", "init", "-q", str(root)], check=True)


def verdict(release: Path, root: Path, command: str = "validate") -> dict[str, Any]:
    done = subprocess.run(
        [sys.executable, "-m", "archkeel", command, "--root", str(root), "--json"],
        cwd=ROOT, env={**os.environ, "ARCHKEEL_CORE_BINARY": str(release)},
        capture_output=True, text=True, check=False,
    )
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    return result


@pytest.mark.parametrize("command", ["validate", "report"])
def test_python_project_gets_a_verdict(release: Path, tmp_path: Path, command: str) -> None:
    project(tmp_path)
    result = verdict(release, tmp_path, command)
    assert result["rules"]["FORBID"][1] == "PASS", result


@pytest.mark.parametrize("source", ["import app.service\n", "from . import service\n", "from app.service import VALUE\n"])
def test_forbidden_import_names_its_site(release: Path, tmp_path: Path, source: str) -> None:
    project(tmp_path, source)
    result = verdict(release, tmp_path)
    assert result["rules"]["FORBID"][1] == "FAIL", result
    assert "src/app/client.py" in json.dumps(result), result
