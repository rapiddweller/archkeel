# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

import pytest

from archkeel.check.onboarding import (
    detect_source,
    interface_entries,
)
from archkeel.check.ports import FilesToWrite
from archkeel.cli import main
from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.model import (
    ArchitectureContract,
    DiagnosticError,
)

_REAL_RATIONALE = "The owners decided this on purpose."


def test_files_to_write_is_an_ordered_immutable_value() -> None:
    entries = (("second.bin", b"\x00\xff"), ("first.txt", b"first\n"))
    files = FilesToWrite(entries)

    assert FilesToWrite().entries == ()
    assert files.entries == entries
    assert list(dict(files.entries)) == ["second.bin", "first.txt"]
    assert not isinstance(files, Mapping)
    with pytest.raises(FrozenInstanceError):
        files.entries = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        iter(files)


def _contract(path: Path) -> ArchitectureContract:
    return parse_contract(decode_json(path.read_bytes()))


def _repository(root: Path, packages: tuple[str, ...] = ("archkeel",)) -> Path:
    for package in packages:
        files = {
            "ir/model.ts": "export const VALUE = 1;\n",
            "cli/app.ts": "import { VALUE } from '../ir/model';\nexport { VALUE };\n",
            "check/rules.ts": (
                "import { VALUE } from '../ir/model';\n"
                "import { EXTRA } from './nested/extra';\nexport const TOTAL = VALUE + EXTRA;\n"
            ),
            "check/nested/extra.ts": "export const EXTRA = 2;\n",
        }
        for name, source in files.items():
            path = root / "src" / package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
    (root / "package.json").write_text(json.dumps({"name": packages[0]}))
    (root / "tsconfig.json").write_text('{"include":["src"]}\n')
    for args in (
        ("init", "-q"),
        ("config", "user.email", "init@example.invalid"),
        ("config", "user.name", "Archkeel init"),
        ("add", "."),
        ("commit", "-qm", "snapshot"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def _init(root: Path, capsys: pytest.CaptureFixture) -> dict:
    assert main(["init", "--root", str(root), "--json", "--full"]) == 0
    return json.loads(capsys.readouterr().out)


def _second_return_type(func: Callable[..., object]) -> type:
    """The declared type of a 2-tuple return's second element, as CHECK-TYPES-DECLARED reads it.

    `boundary_types` (AD-58/AD-63) judges the annotation itself, not a runtime value: a bare
    `dict`/`Dict`/`object`, or a `dict[...]`/`Dict[...]` generic, is the violation regardless of
    what a particular call happens to return. Reading it through `get_type_hints`/`get_origin`
    mirrors that same judgement instead of asserting on one call's runtime type.
    """
    (_, files_type) = get_args(get_type_hints(func)["return"])
    return get_origin(files_type) or files_type


def _flat_layout(root: Path, pyproject: str | None) -> Path:
    for package in ("archkeel_core", "tests_pkg"):
        (root / package).mkdir()
        (root / package / "__init__.py").touch()
    if pyproject is not None:
        (root / "pyproject.toml").write_text(pyproject)
    return root


@pytest.mark.parametrize("name", ["archkeel_core", "Archkeel-Core", "archkeel.core"])
def test_detect_source_matches_the_project_name_in_wheel_file_name_form(
    tmp_path: Path, name: str
) -> None:
    root = _flat_layout(tmp_path, f'[project]\nname = "{name}"\n')
    assert detect_source(root) == ("archkeel_core", "archkeel_core")


def test_detect_source_uses_root_package_when_src_has_no_python_package(tmp_path: Path) -> None:
    root = tmp_path
    (root / "shop").mkdir()
    (root / "shop" / "__init__.py").touch()
    (root / "pyproject.toml").write_text('[project]\nname = "shop"\n')
    (root / "src" / "rust_crate" / "src").mkdir(parents=True)
    (root / "src" / "rust_crate" / "Cargo.toml").touch()

    assert detect_source(root) == ("shop", "shop")


def test_detect_source_keeps_src_when_it_has_a_python_package(tmp_path: Path) -> None:
    root = tmp_path
    (root / "shop").mkdir()
    (root / "shop" / "__init__.py").touch()
    (root / "src" / "shop").mkdir(parents=True)
    (root / "src" / "shop" / "__init__.py").touch()
    (root / "pyproject.toml").write_text('[project]\nname = "shop"\n')

    assert detect_source(root) == ("src/shop", "shop")


@pytest.mark.parametrize("ignored_root", ["docs", ".venv"])
def test_detect_source_finds_namespace_package_without_scanning_irrelevant_roots(
    tmp_path: Path, ignored_root: str
) -> None:
    (tmp_path / "shop" / "app").mkdir(parents=True)
    (tmp_path / "shop" / "app" / "orders.py").touch()
    decoy = tmp_path / ignored_root / "generated_package"
    decoy.mkdir(parents=True)
    (decoy / "__init__.py").touch()
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "{ignored_root}"\n')

    assert detect_source(tmp_path) == ("shop", "shop")


@pytest.mark.parametrize("decoy_root", [".tox", "bad-name"])
def test_detect_source_ignores_hidden_and_non_identifier_roots(
    tmp_path: Path, decoy_root: str
) -> None:
    (tmp_path / "shop" / "app").mkdir(parents=True)
    (tmp_path / "shop" / "app" / "orders.py").touch()
    decoy = tmp_path / decoy_root / "generated_package"
    decoy.mkdir(parents=True)
    (decoy / "__init__.py").touch()
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "unmatched"\n')

    assert detect_source(tmp_path) == ("shop", "shop")


def test_detect_source_does_not_follow_out_of_root_package_symlink(tmp_path: Path) -> None:
    (tmp_path / "shop" / "app").mkdir(parents=True)
    (tmp_path / "shop" / "app" / "orders.py").touch()
    with tempfile.TemporaryDirectory(dir=tmp_path.parent) as external_dir:
        external = Path(external_dir)
        (external / "__init__.py").touch()
        try:
            (tmp_path / "linked_package").symlink_to(external, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"directory symlinks unavailable: {error}")
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "linked-package"\n')

        assert detect_source(tmp_path) == ("shop", "shop")


def test_detect_source_stays_ambiguous_for_multiple_namespace_packages(tmp_path: Path) -> None:
    for name in ("alpha", "beta"):
        package = tmp_path / name / "api"
        package.mkdir(parents=True)
        (package / "routes.py").touch()
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "unmatched"\n')

    with pytest.raises(DiagnosticError) as raised:
        detect_source(tmp_path)

    assert "found alpha, beta" in raised.value.diagnostic.unknown_claim


def test_detect_source_names_root_search_when_src_has_no_python_package(tmp_path: Path) -> None:
    (tmp_path / "src" / "rust_crate").mkdir(parents=True)
    (tmp_path / "src" / "rust_crate" / "Cargo.toml").touch()

    with pytest.raises(DiagnosticError) as raised:
        detect_source(tmp_path)

    assert "found none. Searched directories `src`, `.`." in raised.value.diagnostic.unknown_claim


@pytest.mark.parametrize("pyproject", [None, "[project\n", '[project]\nversion = "1"\n'])
def test_detect_source_fails_closed_without_a_readable_project_name(
    tmp_path: Path, pyproject: str | None
) -> None:
    with pytest.raises(DiagnosticError) as raised:
        detect_source(_flat_layout(tmp_path, pyproject))
    assert raised.value.diagnostic.kind == "scope_empty"
    assert "[project] name (missing); found archkeel_core, tests_pkg." in (
        raised.value.diagnostic.unknown_claim
    )
    assert raised.value.diagnostic.unknown_claim.endswith("Searched directories `.`.")


def test_interface_entries_applies_the_ad9_module_entry_rule() -> None:
    # __all__ present -> module entry regardless of how many names are used.
    assert interface_entries("pkg.mod", {"a"}, False, True, {"a", "b"}) == ["pkg.mod"]
    # Whole-module or star import -> module entry regardless of names.
    assert interface_entries("pkg.mod", set(), True, False, set()) == ["pkg.mod"]
    # 2 of 4 public names used -> half rule qualifies -> one module entry.
    assert interface_entries("pkg.mod", {"a", "b"}, False, False, {"a", "b", "c", "d"}) == [
        "pkg.mod"
    ]
    # 1 of 4 -> below half -> a symbol entry per used name.
    assert interface_entries("pkg.mod", {"a"}, False, False, {"a", "b", "c", "d"}) == ["pkg.mod:a"]
    # Underscore names are never proposed, and they do not count toward the half rule.
    assert interface_entries(
        "pkg.mod", {"_hidden", "shown"}, False, False, {"shown", "b", "c", "d"}
    ) == ["pkg.mod:shown"]
