# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TypeScript onboarding through the in-package source process."""

import json
import subprocess
from pathlib import Path

import pytest

from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_contract, parse_observation
from archkeel.ir.identity import module_identity


def repository(root: Path, files: dict[str, str]) -> Path:
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    config = root / "config/project.json"
    config.parent.mkdir(exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "compilerOptions": {"module": "NodeNext", "moduleResolution": "NodeNext"},
                "include": ["../src", "../workers"],
            }
        )
    )
    for args in (
        ("init", "-q"),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"),
        ("commit", "--allow-empty", "-qm", "empty snapshot"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def arguments(root: Path) -> list[str]:
    return [
        "init",
        "--root",
        str(root),
        "--language",
        "typescript",
        "--source",
        "src",
        "--namespace",
        "client.app",
        "--tsconfig",
        "config/project.json",
        "--json",
    ]


def test_typescript_init_groups_untracked_physical_files_and_persists_settings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(
        tmp_path,
        {
            "src/main.ts": "import './feature/service.js';",
            "src/feature/service.ts": "export const value = 1;",
            "src/name.test.ts": "export {};",
            "src/name/test.ts": "export {};",
            "src/a-b/value.ts": "export {};",
            "src/a_b/value.ts": "export {};",
            "workers/job.ts": "export {};",
        },
    )
    assert subprocess.check_output(["git", "ls-files"], cwd=root) == b""
    assert main([*arguments(root), "--source", "workers"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["observation_complete"] == "PASS"
    config = load_config(root)
    assert config.language == "typescript"
    assert config.roots == ("src", "workers")
    assert config.namespace == "client.app"
    assert config.tsconfig == "config/project.json"
    assert config.collector_argv is None
    contract = parse_contract(decode_json((root / config.contract).read_bytes()))
    feature = module_identity(config.namespace, "src/feature")
    assert any(
        item.packages == (feature,) and item.namespace == feature for item in contract.components
    )
    for file in ("src/main.ts", "src/name.test.ts", "workers/job.ts"):
        module = module_identity(config.namespace, file)
        assert any(
            item.exact_modules == (module,) and not item.packages for item in contract.components
        )
    assert len(contract.components) == 7
    assert sum(item["modules"] for item in result["draft_sizes"]) == 7
    assert len({item.id for item in contract.components}) == 7
    assert result["open_decision_count"] == 42
    assert result["open_decisions_complete"] is False
    assert len(result["open_decisions"]) < result["open_decision_count"]
    assert all(item["observed"] for item in result["open_decisions"])
    assert any(item["import_sites"] == 1 for item in result["open_decisions"])
    assert main([*arguments(root), "--source", "workers", "--full", "--force"]) == 0
    full_result = json.loads(capsys.readouterr().out)
    assert full_result["open_decision_count"] == 42
    assert full_result["open_decisions_complete"] is True
    assert len(full_result["open_decisions"]) == full_result["open_decision_count"]
    assert main(["report", "--root", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["observation_complete"] == "PASS"


def test_typescript_init_uses_the_in_package_collector_without_persisting_host_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path, {"src/main.ts": "export {};"})
    assert main(arguments(root)) == 0
    capsys.readouterr()
    config = load_config(root)
    assert config.collector_argv is None
    text = (root / "archkeel.toml").read_text()
    assert str(root) not in text
    assert "collector_argv" not in text
    assert "node" not in text


def test_typescript_init_supports_explicit_runtime_and_declaration_file_roots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(
        tmp_path,
        {
            "src/main.ts": "import hosts = require('../supportedHosts.cjs');",
            "supportedHosts.cjs": "module.exports = [require('node:os').platform()];",
            "supportedHosts.d.cts": "declare const hosts: readonly string[]; export = hosts;",
            "unselected.ts": "import './missing.js';",
        },
    )
    roots = ("src", "supportedHosts.cjs", "supportedHosts.d.cts")
    assert main([*arguments(root), "--source", roots[1], "--source", roots[2]]) == 0
    result = json.loads(capsys.readouterr().out)
    assert sum(item["modules"] for item in result["draft_sizes"]) == 3
    config = load_config(root)
    assert config.roots == roots
    contract = parse_contract(decode_json((root / config.contract).read_bytes()))
    for source in roots[1:]:
        expected = module_identity(config.namespace, source)
        assert any(component.exact_modules == (expected,) for component in contract.components)
    artifact = root / "report.json"
    assert main(["report", "--root", str(root), "--output", str(artifact), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["observation_complete"] == "PASS"
    observation = parse_observation(decode_canonical_model(decode_json(artifact.read_bytes())))
    assert observation.source.scope == ("src/**", *roots[1:])
    assert {item.data.get("file") for item in observation.records("modules") or ()} == {
        "src/main.ts",
        *roots[1:],
    }
    assert any(
        item.data.get("target_module") == module_identity(config.namespace, roots[1])
        for item in observation.records("imports") or ()
    )


def test_typescript_file_root_cannot_escape_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path / "outside.cjs"
    outside.write_text("module.exports = [];")
    root = repository(tmp_path / "project", {"src/main.ts": "export {};"})
    (root / "host.cjs").symlink_to(outside)
    assert main([*arguments(root), "--source", "host.cjs"]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostics"]
    assert not (root / "archkeel.toml").exists()


@pytest.mark.parametrize("language,source", [("python", "sample.py"), ("dart", "sample.dart")])
def test_python_and_dart_still_reject_file_roots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], language: str, source: str
) -> None:
    root = repository(tmp_path, {source: ""})
    assert (
        main(
            [
                "init",
                "--root",
                str(root),
                "--language",
                language,
                "--source",
                source,
                "--namespace",
                "sample",
                "--json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["diagnostics"]
    assert not (root / "archkeel.toml").exists()


def test_typescript_init_refuses_incomplete_observation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path, {"src/main.ts": "import './missing.js';"})
    assert main([*arguments(root)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["diagnostics"]
    assert not (root / "archkeel.toml").exists()
    assert not (root / "architecture-contract.json").exists()


@pytest.mark.parametrize(
    ("option", "value"),
    [("--source", "../outside"), ("--tsconfig", "config/missing.json")],
)
def test_typescript_init_rejects_invalid_project_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], option: str, value: str
) -> None:
    root = repository(tmp_path, {"src/main.ts": "export {};"})
    argv = arguments(root)
    argv[argv.index(option) + 1] = value
    assert main([*argv]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostics"]
    assert not (root / "archkeel.toml").exists()
    assert not (root / "architecture-contract.json").exists()


@pytest.mark.parametrize("removed", ["--source", "--namespace", "--tsconfig"])
def test_typescript_init_requires_explicit_inputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], removed: str
) -> None:
    root = repository(tmp_path, {"src/main.ts": "export {};"})
    argv = arguments(root)
    index = argv.index(removed)
    del argv[index : index + 2]
    assert main([*argv]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["diagnostics"]
    assert not (root / "archkeel.toml").exists()


@pytest.mark.parametrize(
    ("language", "source", "files"),
    [
        (
            "python",
            "sample",
            {
                "sample/__init__.py": "",
                "sample/core.py": "value = 1",
                "pyproject.toml": '[project]\nname = "sample"\nrequires-python = ">=3.11"\n',
            },
        ),
        ("dart", "lib", {"lib/core/api.dart": "const value = 1;"}),
    ],
)
def test_explicit_python_and_dart_onboarding_remains_available(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    language: str,
    source: str,
    files: dict[str, str],
) -> None:
    root = repository(tmp_path, files)
    assert (
        main(
            [
                "init",
                "--root",
                str(root),
                "--language",
                language,
                "--source",
                source,
                "--namespace",
                "sample",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["observation_complete"] == "PASS"
    config = load_config(root)
    assert config.language == language
    assert config.tsconfig is None
    assert config.collector_argv is None
