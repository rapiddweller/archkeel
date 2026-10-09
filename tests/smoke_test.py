# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Verify that an installed distribution can scan without another checkout."""

import json
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    schemas = files("archkeel").joinpath("schema")
    result_schema = json.loads(
        schemas.joinpath("command-result.schema.json").read_text(encoding="utf-8")
    )
    assert result_schema["$id"] == "urn:archkeel:command-result:6.0.0"
    assert "expectation_fulfilled" in result_schema["required"]
    for name in (
        "architecture-ir-common.schema.json",
        "architecture-ir-python-decoded.schema.json",
        "architecture-contract.schema.json",
        "architecture-projection.schema.json",
        "architecture-command.schema.json",
    ):
        assert json.loads(schemas.joinpath(name).read_text(encoding="utf-8"))["$id"]
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
            "schema_version": "2.1.0",
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
            encoding="utf-8",
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
            encoding="utf-8",
        )
        assert validate.returncode == 0, (validate.stdout, validate.stderr)
        assert json.loads(validate.stdout)["diagnostics"] == []

        def cli(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, "-m", "archkeel.cli", *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        version = cli("--version")
        assert version.returncode == 0 and version.stdout.startswith("archkeel "), version
        skill = cli("skill", "install", "codex", "--root", str(root), "--json")
        assert skill.returncode == 0, (skill.stdout, skill.stderr)
        assert "archkeel init" in (root / ".agents/skills/archkeel/SKILL.md").read_text(
            encoding="utf-8"
        )
        init = cli("init", "--root", str(root), "--force", "--json")
        assert init.returncode == 0, (init.stdout, init.stderr)
        drafted = cli("validate", "--root", str(root), "--json")
        assert drafted.returncode == 2, (drafted.stdout, drafted.stderr)
        diagnostics = [
            (item["code"], item["subject"], item["pointer"])
            for item in json.loads(drafted.stdout)["diagnostics"]
        ]
        assert diagnostics == [
            ("rule.violated", "ASSIGNMENT-COMPLETE", "/rules/0"),
            ("rationale.placeholder", "ASSIGNMENT-COMPLETE", "/rules/0/rationale"),
            ("rationale.placeholder", "COMPONENT-NO-CYCLES", "/rules/1/rationale"),
        ], diagnostics


def typescript() -> None:
    """A TypeScript scan needs only the installed distribution: no Node, no adapter package."""
    with TemporaryDirectory(prefix="archkeel-smoke-ts-") as temporary:
        root = Path(temporary)
        (root / "src").mkdir()
        (root / "src/a.ts").write_text('import { b } from "./b";\nexport const a = b;\n')
        (root / "src/b.ts").write_text("export const b = 1;\n")
        (root / "tsconfig.json").write_text(
            '{"compilerOptions": {"module": "esnext", "moduleResolution": "bundler"},'
            ' "include": ["src"]}\n'
        )
        (root / "architecture-contract.json").write_text(
            '{"schema_version": "2.1.0", "components": [], "rules": []}\n'
        )
        (root / "archkeel.toml").write_text(
            '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
        )
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
            [sys.executable, "-m", "archkeel.cli", "report", "--root", str(root)]
            + ["--output", str(output)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert run.returncode == 0, (run.stdout, run.stderr)
        assert json.loads(run.stdout)["observation_complete"] == "PASS"
        report = json.loads(output.read_text(encoding="utf-8"))
        assert len(report["dependency_edges"]) == 1, report["dependency_edges"]
        # The collector that ran is the installed Python one, not an npm adapter on Node.
        assert report["runtime"]["name"] == "python", report["runtime"]
        assert report["producer"]["name"] == "archkeel-typescript-imports", report["producer"]


def dart() -> None:
    """Exercise installed Dart analysis with no usable Dart executable."""
    with TemporaryDirectory(prefix="archkeel-smoke-dart-") as temporary:
        root = Path(temporary)
        (root / "lib").mkdir()
        (root / "lib/item.dart").write_text(
            "class Item {\n  final String id;\n  Item(this.id);\n  String label() => id;\n}\n"
        )
        (root / "pubspec.yaml").write_text("name: smoke_app\nversion: 0.1.0\n")
        (root / "architecture-contract.json").write_text(
            '{"schema_version":"2.1.0","components":[],"rules":[]}\n'
        )
        (root / "archkeel.toml").write_text(
            '[scan]\nlanguage = "dart"\nroots = ["lib"]\nnamespace = "sample"\n'
            'contract = "architecture-contract.json"\n'
        )
        for args in (
            ("init", "-q"),
            ("config", "user.email", "smoke@example.invalid"),
            ("config", "user.name", "Archkeel smoke test"),
            ("add", "."),
            ("commit", "-qm", "Dart smoke fixture"),
        ):
            subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
        output = root / "architecture.json"
        report = subprocess.run(
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
            encoding="utf-8",
            env={**os.environ, "DART_EXECUTABLE": str(root / "absent-dart")},
        )
        assert report.returncode == 0, (report.stdout, report.stderr)
        assert json.loads(report.stdout)["observation_complete"] == "PASS"
        from archkeel.ir.codec import decode_canonical_model, parse_observation
        from archkeel.ir.source_graph import observed_graph

        observation = parse_observation(
            decode_canonical_model(json.loads(output.read_text(encoding="utf-8")))
        )
        assert observation.producer and observation.producer.name == "archkeel-dart-analyzer"
        assert observation.runtime and observation.runtime.name == "python"
        assert any(
            item.kind == "class" and item.qualified_name == "sample.item.Item"
            for item in observed_graph(observation).entities
        )


if __name__ == "__main__":
    main()
    typescript()
    dart()
