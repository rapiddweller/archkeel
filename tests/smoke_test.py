# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Verify that an installed distribution can scan without another checkout."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    with TemporaryDirectory(prefix="archkeel-smoke-") as temporary:
        root = Path(temporary)
        (root / "sample").mkdir()
        (root / "sample/__init__.py").write_text("value = 1\n")
        provenance = root / "docs/architecture/contract.md"
        provenance.parent.mkdir(parents=True)
        provenance.write_text(
            "# Architecture\n\n<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n```\n"
        )
        contract = {
            "schema_version": "2.0.0",
            "components": [],
            "rules": [],
            "declarations": {
                "capabilities": [
                    {
                        "id": "CAP-SAMPLE",
                        "name": "sample",
                        "label": "Sample",
                        "review_order": 1,
                        "provenance": ["docs/architecture/contract.md"],
                    }
                ],
                "public_api_provenance": ["docs/architecture/contract.md"],
                "context_roots_provenance": ["docs/architecture/contract.md"],
            },
        }
        (root / "architecture-contract.json").write_text(json.dumps(contract))
        (root / "archkeel.toml").write_text(
            '[scan]\nroots = ["sample"]\nnamespace = "sample"\n'
            'contract = "architecture-contract.json"\n'
        )
        (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
        for args in (
            ("init", "-q"),
            ("config", "user.email", "smoke@example.invalid"),
            ("config", "user.name", "Archkeel smoke test"),
            ("add", "."),
            ("commit", "-qm", "smoke fixture"),
        ):
            subprocess.run(["git", *args], cwd=root, check=True)
        output = root / "architecture.json"
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "archkeel.cli",
                "report",
                "--root",
                str(root),
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
        result = json.loads(run.stdout)
        assert run.returncode == 0, (run.stdout, run.stderr)
        assert result["observation_complete"] == "PASS"
        assert result["declared_rules"] == "PASS"
        assert result["diagnostics"] == []
        assert output.is_file()
        validate = subprocess.run(
            [sys.executable, "-m", "archkeel.cli", "validate", "--root", str(root), "--json"],
            capture_output=True,
            text=True,
        )
        assert validate.returncode == 0, (validate.stdout, validate.stderr)
        assert json.loads(validate.stdout)["diagnostics"] == []

        def cli(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, "-m", "archkeel.cli", *args], capture_output=True, text=True
            )

        version = cli("--version")
        assert version.returncode == 0 and version.stdout.startswith("archkeel "), version
        skill = cli("skill", "install", "codex", "--root", str(root), "--json")
        assert skill.returncode == 0, (skill.stdout, skill.stderr)
        assert "archkeel init" in (root / "AGENTS.md").read_text()
        init = cli("init", "--root", str(root), "--force", "--json")
        assert init.returncode == 0, (init.stdout, init.stderr)
        drafted = cli("validate", "--root", str(root), "--json")
        pointers = {item["pointer"] for item in json.loads(drafted.stdout)["diagnostics"]}
        assert drafted.returncode == 2 and pointers == {"/rules/0/rationale", "/rules/1/rationale"}


if __name__ == "__main__":
    main()
