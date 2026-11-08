# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The one owner of the two coverage questions (#880 step S3, AD-322).

D3 asks whether an observation is complete. D4 asks whether the scan roots contain the physical
domain of a source scope.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from test_architecture_coverage_characterization import _STATES, _in_state
from test_architecture_owner_characterization import _ownership_model
from test_decisions import _declaration

from archkeel.check.evaluation.rules import _cycle_scan_coverage
from archkeel.ir.coverage import (
    observation_complete,
    observation_covers_rule,
    scan_covers_exact_modules,
    scan_covers_packages,
    under_roots,
)
from archkeel.ir.model import ArchitectureContract
from archkeel.ir.profiles import Profile, profile_for

_SRC = Path(__file__).resolve().parents[1] / "src" / "archkeel"
_PYTHON = profile_for("archkeel-python-analyzer")
_TYPESCRIPT = profile_for("archkeel-typescript-imports")
_TREE = (
    ("sample", "src/sample/__init__.py"),
    ("sample.core", "src/sample/core/__init__.py"),
    ("sample.core.a", "src/sample/core/a.py"),
)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("pass", True),
        ("pass with failures", False),
        ("fail", False),
        ("fail with failures", False),
    ],
)
def test_an_observation_is_complete_only_with_a_pass_and_no_failure(
    state: str, expected: bool
) -> None:
    """A recorded failure is missing evidence, so a PASS status next to it is not complete."""
    assert state in _STATES
    model = _in_state(_ownership_model(), state)
    assert observation_complete(model.coverage) is expected


def test_a_rule_without_a_source_name_covers_nothing() -> None:
    model = _ownership_model()
    assert not observation_covers_rule(model, _declaration("RULE", "source_ownership", ()))
    assert not observation_covers_rule(
        model, _declaration("RULE", "source_ownership", (("source", 3),))
    )


def test_scan_covers_packages_needs_a_module_and_a_root() -> None:
    assert scan_covers_packages(("sample",), _TREE, _PYTHON, ("src",))
    assert not scan_covers_packages(("sample",), _TREE, _PYTHON, ())
    assert not scan_covers_packages(("sample",), (), _PYTHON, ("src",))
    assert not scan_covers_packages(("other",), _TREE, _PYTHON, ("src",))
    assert not scan_covers_packages((), _TREE, _PYTHON, ("src",))


def test_scan_covers_packages_does_not_skip_a_module_it_cannot_place() -> None:
    """The file of `sample.a.b.c` is not where its name says. The domain is unknown, so the scope
    is not covered. This is the rule that `rules` always had. The copy in `decisions` skipped
    such a module and called the scope covered (AD-322)."""
    modules = (*_TREE, ("sample.a.b.c", "x.py"))
    assert not scan_covers_packages(("sample",), modules, _PYTHON, ("src",))
    assert scan_covers_packages(("sample",), _TREE, _PYTHON, ("src",))


def test_scan_covers_packages_needs_every_physical_prefix_under_a_root() -> None:
    """Two prefixes, src/sample and lib/sample: one root covers only the first.

    A mutant that needs only one covered prefix (`any` instead of `all`) returns True here."""
    modules = (
        ("sample.core", "src/sample/core/__init__.py"),
        ("sample.peer", "lib/sample/peer/__init__.py"),
    )
    assert not scan_covers_packages(("sample",), modules, _PYTHON, ("src",))
    assert scan_covers_packages(("sample",), modules, _PYTHON, (".",))
    assert scan_covers_packages(("sample",), modules, _PYTHON, ("src", "lib"))


def test_scan_covers_packages_reads_a_file_of_another_language_by_its_directory() -> None:
    modules = (("sample.core", "src/sample/core.ts"), ("sample.peer", "src/sample/peer.ts"))
    assert scan_covers_packages(("sample",), modules, _TYPESCRIPT, ("src",))
    assert not scan_covers_packages(("sample",), modules, _TYPESCRIPT, ("lib",))


def test_scan_covers_packages_follows_a_deep_module_up_to_the_package_directory() -> None:
    """A file of another language sits below its package: `sample.a.b.c` in src/sample/a/b/c.ts
    belongs to the package `sample`, so the domain is src/sample. A mutant that steps one parent
    more or less moves the domain out of this root or into the next one."""
    modules = (("sample.a.b.c", "src/sample/a/b/c.ts"),)
    assert scan_covers_packages(("sample",), modules, _TYPESCRIPT, ("src/sample",))
    assert not scan_covers_packages(("sample",), modules, _TYPESCRIPT, ("src/sample/a",))


def test_scan_covers_packages_does_not_place_a_module_in_a_file_with_a_dot_in_its_name() -> None:
    """The file core.x.py has the stem `core.x`, so it cannot hold `sample.core.x` below the
    package `sample.core`. The domain is unknown and the scope is not covered."""
    modules = (("sample.core.x", "src/sample/core.x.py"),)
    assert not scan_covers_packages(("sample.core",), modules, _PYTHON, ("src",))
    assert scan_covers_packages(("sample.core.x",), modules, _PYTHON, ("src",))


def test_scan_covers_packages_places_a_module_in_a_folder_of_another_name_as_unknown() -> None:
    """The file is in `other/`, but the name says `sample`: no layout explains it."""
    modules = (("sample.core", "src/other/core.py"),)
    assert not scan_covers_packages(("sample",), modules, _PYTHON, ("src",))


@pytest.mark.parametrize(
    ("package", "profile", "modules", "root"),
    [
        ("sample", _PYTHON, (("sample", "src/sample.py"),), "src/sample.py"),
        ("sample", _PYTHON, (("sample", "src/sample/__init__.py"),), "src/sample/__init__.py"),
        ("a", _TYPESCRIPT, (("a", "src/a.ts"),), "src/a.ts"),
    ],
)
def test_a_root_that_names_the_file_itself_does_not_cover_it(
    package: str, profile: Profile, modules: tuple[tuple[str, str], ...], root: str
) -> None:
    """The domain of a package is a directory. A root that is the file of the module only is
    not that directory, so it covers nothing (AD-322). The old copy in `decisions` said covered."""
    assert not scan_covers_packages((package,), modules, profile, (root,))
    assert scan_covers_packages((package,), modules, profile, (str(Path(root).parent),))


def test_an_absolute_root_does_not_cover_an_absolute_file_path() -> None:
    """The roots and the files of a scan are relative. Real collectors record relative paths.
    The old copy in `decisions` let an absolute root cover an absolute file (AD-322)."""
    modules = (("sample", "/abs/src/sample/__init__.py"),)
    assert not scan_covers_packages(("sample",), modules, _PYTHON, ("/abs/src",))
    assert not under_roots("/abs/src/a.py", ("/abs/src",))


def test_a_scan_whose_module_records_lack_a_name_or_a_file_is_not_covered() -> None:
    """The cycle check of a project-closure language reads every module record. A record
    without a name or a file is no module. With none left, the namespace is not covered (before:
    KeyError)."""
    contract = ArchitectureContract(schema_version="3.2.0", components=(), rules=())
    good: Any = {"id": "M", "data": {"qualified_name": "sample", "file": "src/sample.ts"}}
    for modules in ([{"id": "M", "data": {}}], [{"id": "M", "data": {"qualified_name": "sample"}}]):
        covered = _cycle_scan_coverage(contract, modules, _TYPESCRIPT, ("src",), "sample")
        assert covered == (False, ())
    assert _cycle_scan_coverage(contract, [good], _TYPESCRIPT, ("src",), "sample") == (True, ())


def test_scan_covers_exact_modules_rejects_an_absolute_root() -> None:
    """The roots of a scan are relative. A mutant that lets an absolute root contain a path
    returns True here."""
    modules = (("sample", "/abs/src/sample.py"),)
    assert not scan_covers_exact_modules(("sample",), modules, ("/abs/src",))


def test_scan_covers_exact_modules_needs_every_exact_module_under_a_root() -> None:
    """A mutant that checks only the first exact module returns True here."""
    modules = (("sample.a", "src/sample/a.py"), ("sample.b", "lib/sample/b.py"))
    assert scan_covers_exact_modules(("sample.a",), modules, ("src",))
    assert not scan_covers_exact_modules(("sample.a", "sample.b"), modules, ("src",))


def test_scan_covers_exact_modules_needs_a_root() -> None:
    """With no exact module and a root the scope is covered. With no root it never is."""
    assert not scan_covers_exact_modules(("sample.a",), (("sample.a", "src/a.py"),), ())
    assert not scan_covers_exact_modules((), (), ())
    assert scan_covers_exact_modules((), (), ("src",))


@pytest.mark.parametrize(
    ("path", "roots", "expected"),
    [
        ("src/a.py", ("src",), True),
        ("src/a.py", ("./src",), True),
        ("src/a.py", (".",), True),
        ("src/a.py", ("src/b",), False),
        ("src/a.py", ("/src",), False),
        ("src/a.py", (), False),
        ("srcs/a.py", ("src",), False),
    ],
)
def test_under_roots_reads_relative_roots_by_path_parts(
    path: str, roots: tuple[str, ...], expected: bool
) -> None:
    assert under_roots(path, roots) is expected


@pytest.mark.parametrize(
    ("file", "names"),
    [
        (
            "ir/decisions.py",
            (
                "_source_scope_covers_rule",
                "_qualified_module_under_source",
                "_physical_source_prefix",
                "_physical_path_covered",
            ),
        ),
        (
            "check/evaluation/rules.py",
            (
                "_scan_covers_packages",
                "_scan_covers_exact_modules",
                "_package_paths",
                "_relative_path",
                "_contains",
            ),
        ),
    ],
)
def test_the_copies_of_the_scan_root_coverage_are_gone(file: str, names: tuple[str, ...]) -> None:
    """Only `coverage` defines these. Another definition is a second copy."""
    text = (_SRC / file).read_text(encoding="utf-8")
    for name in names:
        assert re.search(rf"^def {name}\b", text, re.MULTILINE) is None, f"{file} defines {name}"


def test_no_module_spells_the_completeness_of_an_observation_again() -> None:
    """`coverage.status == Verdict.PASS` is the spelling of the status alone. Only `coverage`
    combines it with the failures. `model` stays: it checks the diagnostics invariant."""
    found = [
        f"{path.relative_to(_SRC)}:{number}"
        for folder in ("ir", "check")
        for path in sorted((_SRC / folder).rglob("*.py"))
        if path.name not in {"coverage.py", "model.py"}
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"\bcoverage\.status\s*(==|!=|is|is not)\s*_?Verdict\.PASS", line)
    ]
    assert found == []
