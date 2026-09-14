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
        provenance.write_text("# Architecture\n")
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


if __name__ == "__main__":
    main()
