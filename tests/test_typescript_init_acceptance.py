# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent public-command acceptance for TypeScript onboarding."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from archkeel.ir.codec import parse_contract
from archkeel.ir.model import in_scope

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "packages/typescript-adapter/dist/entry.js"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=root, check=True, capture_output=True, text=True
    ).stdout


def _repository(root: Path) -> Path:
    root.mkdir()
    (root / "README.md").write_text("Onboarding acceptance fixture.\n")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "acceptance@example.invalid")
    _git(root, "config", "user.name", "Acceptance")
    _git(root, "add", "README.md")
    _git(root, "-c", "commit.gpgsign=false", "commit", "-qm", "initial")
    return root


def _typescript(root: Path, source: str = "src") -> None:
    files = {
        "domain/order-item.ts": "export const order = 1;\n",
        "domain/index.ts": 'export { order } from "./order-item";\n',
        "domain/_order.ts": "export const other = 2;\n",
        "data-api/client.ts": (
            'import { order } from "../domain/index"; export const client = order;\n'
        ),
        "main.ts": 'import { client } from "./data-api/client"; export const app = client;\n',
        "index.ts": 'export { order } from "./domain/index";\n',
        "domain/order-item.test.ts": 'import "./unavailable-test-only";\n',
    }
    for name, content in files.items():
        path = root / source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (root / "config").mkdir()
    (root / "config/production.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "CommonJS",
                    "moduleResolution": "Node",
                    "noEmit": True,
                },
                "include": [f"../{source}/**/*.ts"],
                "exclude": [f"../{source}/**/*.test.ts"],
            }
        )
    )
    (root / "package.json").write_text(
        json.dumps({"scripts": {"prepare": "touch PROJECT_EXECUTED"}})
    )


def _invoke(root: Path, *args: str, env: dict[str, str] | None = None):
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    environment.update(env or {})
    return subprocess.run(
        (sys.executable, "-m", "archkeel.cli", *args, "--root", str(root), "--json"),
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _init(root: Path, *, source="src", namespace="shop", default=False, env=None):
    assert ADAPTER.is_file(), "Build the pinned TypeScript collector before acceptance."
    args = [
        "init",
        "--language",
        "typescript",
        "--source",
        source,
        "--namespace",
        namespace,
        "--tsconfig",
        "config/production.json",
    ]
    if not default:
        args.extend(("--collector-argv", "node", str(ADAPTER)))
    return _invoke(root, *args, env=env)


@pytest.mark.parametrize(
    ("source", "namespace", "prefix"),
    (
        ("src", "shop", "shop.src"),
        (
            "packages/ide-src/source",
            "workspace.ide",
            "workspace.ide.packages.ide_x2d_src.source",
        ),
    ),
)
def test_untracked_typescript_init_uses_physical_directories_and_path_identity(
    tmp_path: Path, source: str, namespace: str, prefix: str
) -> None:
    root = _repository(tmp_path / "project")
    _typescript(root, source)
    assert _git(root, "ls-files") == "README.md\n"
    result = _init(root, source=source, namespace=namespace)
    assert result.returncode == 0, result.stdout + result.stderr
    draft = parse_contract(json.loads((root / "architecture-contract.json").read_text()))
    domain = next(
        component for component in draft.components if f"{prefix}.domain" in component.packages
    )
    data = next(
        component
        for component in draft.components
        if f"{prefix}.data_x2d_api" in component.packages
    )
    assert domain != data
    assert f"{prefix}.domain.index_x2e_ts" in (domain.public or ())
    assert f"{prefix}.data_x2d_api.client_x2e_ts" in (data.public or ())
    expected = {
        f"{prefix}.domain.order_x2d_item_x2e_ts",
        f"{prefix}.domain.index_x2e_ts",
        f"{prefix}.domain._x5f_order_x2e_ts",
        f"{prefix}.data_x2d_api.client_x2e_ts",
        f"{prefix}.main_x2e_ts",
        f"{prefix}.index_x2e_ts",
    }
    for module in expected:
        owners = [
            component
            for component in draft.components
            if module in (component.exact_modules or ())
            or any(in_scope(module, package) for package in component.packages)
        ]
        assert len(owners) == 1, (module, owners)
    payload = json.loads(result.stdout)
    sizes = {item["label"]: item["modules"] for item in payload["draft_sizes"]}
    assert sizes[domain.label] == 3
    assert sizes[data.label] == 1
    assert sum(sizes.values()) == 6
    assert all(
        ":" not in entry for component in draft.components for entry in component.public or ()
    )
    assert all(
        rule.kind not in {"allowed_dependency", "forbidden_dependency"} for rule in draft.rules
    )
    assert not (root / "PROJECT_EXECUTED").exists()
    scan = tomllib.loads((root / "archkeel.toml").read_text())["scan"]
    assert scan["language"] == "typescript"
    assert scan["roots"] == [source]
    assert scan["namespace"] == namespace
    assert scan["tsconfig"] == "config/production.json"
    assert scan["collector_argv"] == ["node", str(ADAPTER)]
    report = _invoke(root, "report")
    assert report.returncode == 0, report.stdout + report.stderr
    assert json.loads(report.stdout)["coverage"]["files_parsed"] == 6


def test_default_installed_collector_keeps_configuration_portable(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    _typescript(root)
    node = shutil.which("node")
    assert node is not None
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    if os.name == "nt":
        binary = binary_dir / "archkeel-typescript.cmd"
        binary.write_text(f'@"{node}" "{ADAPTER}" %*\n')
    else:
        binary = binary_dir / "archkeel-typescript"
        binary.write_text(f'#!/bin/sh\nexec {shlex.quote(node)} {shlex.quote(str(ADAPTER))} "$@"\n')
        binary.chmod(0o755)
    env = {"PATH": str(binary_dir) + os.pathsep + os.environ["PATH"]}
    result = _init(root, default=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    config_text = (root / "archkeel.toml").read_text()
    scan = tomllib.loads(config_text)["scan"]
    assert scan.get("collector_argv", ["archkeel-typescript"]) == ["archkeel-typescript"]
    assert str(ROOT) not in config_text
    assert str(tmp_path) not in config_text
    assert "npx" not in config_text
    assert _invoke(root, "report", env=env).returncode == 0


def test_missing_collector_does_not_install_or_write_a_draft(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    _typescript(root)
    result = _invoke(
        root,
        "init",
        "--language",
        "typescript",
        "--source",
        "src",
        "--namespace",
        "shop",
        "--tsconfig",
        "config/production.json",
        "--collector-argv",
        "missing-typescript-collector",
    )
    assert result.returncode == 2
    assert {item["kind"] for item in json.loads(result.stdout)["diagnostics"]} == {"missing_tool"}
    assert not (root / "archkeel.toml").exists()
    assert not (root / "architecture-contract.json").exists()
    assert not (root / "node_modules").exists()


@pytest.mark.parametrize("language", ["python", "dart"])
def test_existing_explicit_language_init_still_works(tmp_path: Path, language: str) -> None:
    root = _repository(tmp_path / "project")
    source_arg = "src/shop" if language == "python" else "src"
    source = root / source_arg
    source.mkdir(parents=True)
    if language == "python":
        (root / "pyproject.toml").write_text(
            '[project]\nname = "shop"\nrequires-python = ">=3.11"\n'
        )
        (source / "__init__.py").write_text("")
        (source / "model.py").write_text("VALUE = 1\n")
    else:
        (source / "model.dart").write_text("const value = 1;\n")
    result = _invoke(
        root, "init", "--language", language, "--source", source_arg, "--namespace", "shop"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    scan = tomllib.loads((root / "archkeel.toml").read_text())["scan"]
    assert scan.get("language", "python") == language
    assert "tsconfig" not in scan
    assert "collector_argv" not in scan


def test_repeated_source_roots_preserve_distinct_physical_owners(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    _typescript(root)
    (root / "tools/domain").mkdir(parents=True)
    (root / "tools/domain/check.ts").write_text("export const check = true;\n")
    config_path = root / "config/production.json"
    config = json.loads(config_path.read_text())
    config["include"].append("../tools/**/*.ts")
    config_path.write_text(json.dumps(config))
    result = _invoke(
        root,
        "init",
        "--language",
        "typescript",
        "--source",
        "src",
        "--source",
        "tools",
        "--namespace",
        "shop",
        "--tsconfig",
        "config/production.json",
        "--collector-argv",
        "node",
        str(ADAPTER),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    draft = parse_contract(json.loads((root / "architecture-contract.json").read_text()))
    first = next(
        component for component in draft.components if "shop.src.domain" in component.packages
    )
    second = next(
        component for component in draft.components if "shop.tools.domain" in component.packages
    )
    assert first.id != second.id
    assert sum(item["modules"] for item in json.loads(result.stdout)["draft_sizes"]) == 7
    scan = tomllib.loads((root / "archkeel.toml").read_text())["scan"]
    assert scan["roots"] == ["src", "tools"]
    assert _invoke(root, "report").returncode == 0


@pytest.mark.parametrize("missing", ["source", "namespace", "tsconfig"])
def test_typescript_requires_explicit_scope_and_project_config(
    tmp_path: Path, missing: str
) -> None:
    root = _repository(tmp_path / "project")
    _typescript(root)
    args = ["init", "--language", "typescript"]
    for key, value in (
        ("source", "src"),
        ("namespace", "shop"),
        ("tsconfig", "config/production.json"),
    ):
        if key != missing:
            args.extend((f"--{key}", value))
    args.extend(("--collector-argv", "node", str(ADAPTER)))
    result = _invoke(root, *args)
    assert result.returncode == 2
    assert not (root / "archkeel.toml").exists()
    assert not (root / "architecture-contract.json").exists()


def test_missing_tsconfig_refuses_without_writing_a_draft(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    _typescript(root)
    (root / "config/production.json").unlink()
    result = _init(root)
    assert result.returncode == 2
    assert json.loads(result.stdout)["diagnostics"]
    assert not (root / "archkeel.toml").exists()
    assert not (root / "architecture-contract.json").exists()
