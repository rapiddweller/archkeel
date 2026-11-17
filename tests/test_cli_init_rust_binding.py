# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-784 (#1612): a single Cargo crate is a Rust part, and a stated PyO3 binding is an interface.

The plant is the layout of pydantic: a Python project at the root that depends on a uv workspace
member, and that member is one Cargo crate (no `[workspace]`) built by maturin into the extension
module `app_core._app_core`. Only manifests are read. A Python import of a module with that name,
without the stated binding, makes no interface.
"""

import json
from pathlib import Path

import pytest

from archkeel.cli import core_only
from archkeel.cli.init_draft import SYSTEM
from tests.test_cli_auto_init import commit, write

ROOT_PROJECT = """[project]
name = "app"
version = "0"
requires-python = ">=3.11"
dependencies = ["app-core==1.0.0"]
"""
UV = """
[tool.uv.sources]
app-core = { workspace = true }

[tool.uv.workspace]
members = ["app-core"]
"""
CARGO = """[package]
name = "app-core"
version = "1.0.0"
edition = "2021"

[lib]
name = "_app_core"
crate-type = ["cdylib", "rlib"]

[dependencies]
pyo3 = "0.22"
"""
MATURIN = """[build-system]
requires = ["maturin>=1,<2"]
build-backend = "maturin"

[project]
name = "app_core"
version = "1.0.0"

[tool.maturin]
python-source = "python"
module-name = "app_core._app_core"
bindings = "pyo3"
"""
FILES = {
    "pyproject.toml": ROOT_PROJECT + UV,
    "app/__init__.py": "",
    "app/models/__init__.py": "from app_core import _app_core\n",
    "app/main.py": "from app.models import _app_core\n",
    "app-core/Cargo.toml": CARGO,
    "app-core/pyproject.toml": MATURIN,
    "app-core/build.rs": "fn main() {}\n",
    "app-core/src/lib.rs": "mod errors;\nmod validators;\npub fn run() {}\n",
    "app-core/src/errors.rs": "pub struct Error;\n",
    "app-core/src/validators/mod.rs": "pub fn check() {}\n",
    "app-core/python/app_core/__init__.py": "from ._app_core import run\n",
    "app-core/python/app_core/_app_core.pyi": "def run() -> None: ...\n",
    ".gitignore": "target\n",
}
EDGE = {
    "id": "app-to-app_core-1",
    "source": "app",
    "target": "app_core",
    "title": "Python extension module app_core._app_core (PyO3 binding, maturin)",
    "schema": "app-core/python/app_core/_app_core.pyi",
}


def init(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[dict[str, object], dict]:
    code = core_only.run(["init", "--root", str(root), "--json"])
    document = json.loads(capsys.readouterr().out)
    assert code == 0, document
    return document, json.loads((root / SYSTEM).read_text(encoding="utf-8"))


def test_a_single_crate_is_a_rust_part_with_a_component_for_each_top_module(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document, system = init(commit(write(tmp_path, FILES)), capsys)
    assert document["parts"] == ["Python app", "Rust app_core"]
    assert [part["id"] for part in system["parts"]] == ["app", "app_core"]
    contract = tmp_path / "docs/architecture/app_core/architecture-contract.json"
    components = json.loads(contract.read_text(encoding="utf-8"))["components"]
    selectors = {c["label"]: (c["packages"], c["exact_modules"]) for c in components}
    namespace = "app_core.app_core"
    assert selectors == {
        "errors": ([f"{namespace}.errors"], []),
        "validators": ([f"{namespace}.validators"], []),
        # The collector reads the manifest as the module `cargo_toml` of the crate.
        "root": ([], [namespace, f"{namespace}.build_script", f"{namespace}.cargo_toml"]),
    }


def test_a_stated_pyo3_binding_is_the_interface_from_the_python_part_to_the_rust_part(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = commit(write(tmp_path, FILES))
    document, system = init(root, capsys)
    assert system["interfaces"] == [EDGE]
    assert document["interfaces"] == [EDGE["id"]]

    # The system run is a verdict (no refusal), and its frame names the interface.
    code = core_only.run(["validate", "--root", str(root), "--json"])
    run = json.loads(capsys.readouterr().out)
    assert "refusal" not in run and code in (0, 1, 2), run
    interfaces = run["frame"]["system"]["interfaces"]
    assert [(i["source"], i["target"], i["schema"]) for i in interfaces] == [
        ("app", "app_core", EDGE["schema"])
    ]


def test_the_init_text_says_that_the_interface_is_stated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = core_only.run(["init", "--root", str(commit(write(tmp_path, FILES))), "--text"])
    text = capsys.readouterr().out
    assert code == 0 and "Interfaces: 1 stated by a PyO3 binding (AD-784)." in text, text
    assert "Rust app_core" in text


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"pyproject.toml": ROOT_PROJECT}, "the dependency has no local source"),
        ({"app-core/pyproject.toml": MATURIN.replace("maturin", "setuptools")}, "no maturin"),
        ({"app-core/pyproject.toml": MATURIN.replace('"pyo3"', '"bin"')}, "no extension"),
        (
            {"pyproject.toml": (ROOT_PROJECT + UV).replace("app-core==1.0.0", "other==1")},
            "the project does not depend on the binding",
        ),
    ],
)
def test_without_a_stated_binding_no_interface_is_drafted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: dict[str, str], why: str
) -> None:
    """The Python code imports `app_core._app_core` in every case: a name is never a binding."""
    _, system = init(commit(write(tmp_path, {**FILES, **change})), capsys)
    assert [part["id"] for part in system["parts"]] == ["app", "app_core"], why
    assert system["interfaces"] == [], why


def test_a_crate_below_a_workspace_is_no_part_of_its_own_and_its_binding_targets_the_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {
        **FILES,
        "Cargo.toml": '[workspace]\nmembers = ["app-core", "tool"]\n',
        "tool/Cargo.toml": '[package]\nname = "tool"\nversion = "0.1.0"\nedition = "2021"\n',
        "tool/src/lib.rs": "pub fn t() {}\n",
    }
    _, system = init(commit(write(tmp_path, files)), capsys)
    assert [part["id"] for part in system["parts"]] == ["rust", "app"]
    edge = {**EDGE, "id": "app-to-rust-1", "target": "rust"}
    assert system["interfaces"] == [edge]
