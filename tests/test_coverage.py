# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The one owner of the two coverage questions (#880 step S3, AD-322).

D3 asks whether an observation is complete. D4 asks whether the scan roots contain the physical
domain of a source scope.
"""

import ast
import io
import re
import tokenize
from collections import Counter
from collections.abc import Mapping
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


# The guard finds a spelling of the coverage status next to PASS, outside the owner. It catches
# `==`, `!=`, `is` and `is not` with `Verdict.PASS` or a "PASS" string, on the attribute, the
# `["status"]` key, `.status.value`, `getattr(x, "status")` and a `coverage_status` name, in both
# operand orders. The object name must contain `coverage` as a whole word. It does NOT catch an
# alias or a local that holds the status, a compare split over several lines, an object without
# `coverage` in its name, or `in {Verdict.PASS}`. Docstrings and comments are not read.
_STATUS = (
    r"""(?:(?<!\w)(?:\w+\.)*coverage(?:\.status(?:\.value)?|\[["']status["']\])"""
    r"""|(?<!\w)(?:\w+\.)*coverage_status(?:\.value)?"""
    r"""|getattr\(\s*(?:\w+\.)*coverage\s*,\s*["']status["']\s*\)(?:\.value)?)"""
)
_PASS = r"""(?:_?Verdict\.PASS|["']PASS["'])"""
_OPERATOR = r"(?:==|!=|\bis not\b|\bis\b)"
_STATUS_SPELLING = re.compile(
    rf"{_STATUS}\s*{_OPERATOR}\s*{_PASS}|{_PASS}\s*{_OPERATOR}\s*{_STATUS}"
)
# Each kept spelling asks another question than "is the observation complete". The count is
# exact: a second copy of a kept line is a new spelling.
_NAMED_EXCEPTIONS = {
    ("ir/model.py", "or self.coverage.status != Verdict.PASS"): "the diagnostics invariant",
    (
        "check/observation.py",
        'and scan.coverage["status"] == "PASS"',
    ): "raw scan dict before the observation exists; the next line adds the failures",
    (
        "check/observation.py",
        'if scan.coverage["status"] == "PASS":',
    ): "raw scan dict; asks for a failed scan to recover, and PASS with failures must stay out",
    (
        "check/expectation.py",
        'if delta_model.coverage.status != "PASS":',
    ): "delta status: no failure list exists in a delta",
    (
        "check/expectation.py",
        'delta.baseline.coverage_status != "PASS"',
    ): "snapshot status recorded in a delta: no failure list",
    (
        "check/expectation.py",
        'or delta.head.coverage_status != "PASS"',
    ): "snapshot status recorded in a delta: no failure list",
}

_KEPT = Counter(dict.fromkeys(_NAMED_EXCEPTIONS, 1))


def _code_lines(text: str) -> list[str]:
    """The lines of a module without comments and without docstrings."""
    lines = text.splitlines()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            row, column = token.start
            lines[row - 1] = lines[row - 1][:column]
    for node in ast.walk(ast.parse(text)):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for row in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                lines[row - 1] = ""
    return lines


def _spellings(modules: Mapping[str, str]) -> Counter[tuple[str, str]]:
    return Counter(
        (name, line.strip())
        for name, text in modules.items()
        if name != "ir/coverage.py"
        for line in _code_lines(text)
        if _STATUS_SPELLING.search(line)
    )


def _source_modules() -> dict[str, str]:
    return {
        path.relative_to(_SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(_SRC.rglob("*.py"))
    }


def test_no_module_spells_the_completeness_of_an_observation_again() -> None:
    """A spelling outside the owner and outside the named table is a copy."""
    assert _spellings(_source_modules()) - _KEPT == Counter()


def test_every_named_exception_still_exists_exactly_once() -> None:
    assert _KEPT - _spellings(_source_modules()) == Counter()


def test_a_second_copy_of_a_kept_line_is_a_new_spelling() -> None:
    name, line = "check/observation.py", 'if scan.coverage["status"] == "PASS":'
    assert (name, line) in _NAMED_EXCEPTIONS
    found = _spellings({name: f"{line}\n    pass\n{line}\n    pass\n"})
    assert found[(name, line)] == 2
    assert found - _KEPT == Counter({(name, line): 1})


@pytest.mark.parametrize(
    "line",
    [
        "x = coverage.status == Verdict.PASS",
        'if scan.coverage["status"] == "PASS":',
        "if model.coverage.status is not _Verdict.PASS:",
        "ok = delta.head.coverage_status != 'PASS'",
        'return "PASS" == model.coverage.status',
        'if model.coverage.status.value == "PASS":',
        'if getattr(model.coverage, "status") == Verdict.PASS:',
        'if getattr(model.coverage, "status").value != "PASS":',
    ],
)
def test_the_guard_catches_every_spelling(line: str) -> None:
    assert _STATUS_SPELLING.search(line)


@pytest.mark.parametrize(
    "line",
    [
        'rules = scan.coverage["rules"] != "PASS"',
        "coverage.status == Verdict.FAIL",
        'if test_coverage_status != "PASS":',
        'if my_coverage.status_text == "PASS":',
    ],
)
def test_the_guard_leaves_other_questions_alone(line: str) -> None:
    assert _STATUS_SPELLING.search(line) is None


def test_the_guard_reads_neither_comments_nor_docstrings() -> None:
    text = (
        'def f():\n    """Says coverage.status == Verdict.PASS in prose."""\n'
        '    return 1  # coverage.status == "PASS"\n'
    )
    assert _spellings({"x.py": text}) == Counter()
    assert _spellings({"x.py": 'ok = coverage.status == "PASS"\n'}) == Counter(
        {("x.py", 'ok = coverage.status == "PASS"'): 1}
    )
