# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import ast
import json
import subprocess
import tomllib
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

from tools.file_size import MAX_FILE_LINES, SIZE_LIMIT_EXEMPT, is_size_limited, line_count

ROOT = Path(__file__).parents[1]
TRACKED = tuple(
    ROOT / name
    for name in subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--deduplicate", "-z"],
        cwd=ROOT,
        text=True,
    ).split("\0")
    if name and (ROOT / name).is_file()
)
SOURCES = tuple(
    path for path in TRACKED if path.suffix == ".py" and path.is_relative_to(ROOT / "src")
)
LONG_FUNCTION_LINES = 80
FILE_SIZE_BASELINE = ROOT / "tests/file_size_baseline.json"
ALLOWED_LONG_FUNCTIONS: dict[str, str] = {}


def _functions(node: ast.AST, prefix: str) -> Iterator[tuple[str, int]]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            name = f"{prefix}{child.name}"
            if not isinstance(child, ast.ClassDef):
                yield name, (child.end_lineno or child.lineno) - child.lineno + 1
            yield from _functions(child, f"{name}.")
        else:
            yield from _functions(child, prefix)


def _file_size_problems(
    root: Path, relatives: Iterable[str], baseline: Mapping[str, int]
) -> list[str]:
    sizes = {relative: line_count(root / relative) for relative in relatives}
    problems = []
    for relative, lines in sorted(sizes.items()):
        if lines <= MAX_FILE_LINES and relative in baseline:
            problems.append(f"{relative} has {lines} lines, so remove its entry from the baseline.")
        elif lines > MAX_FILE_LINES and relative not in baseline:
            problems.append(
                f"{relative} has {lines} lines. Split it at a responsibility seam "
                f"to at most {MAX_FILE_LINES} lines."
            )
        elif relative in baseline and lines > baseline[relative]:
            problems.append(
                f"{relative} has {lines} lines and grew past {baseline[relative]}. "
                f"Move code out at a responsibility seam."
            )
        elif relative in baseline and lines < baseline[relative]:
            problems.append(
                f"{relative} has {lines} lines and shrank from {baseline[relative]}. "
                f"Lower its count in the baseline to {lines}."
            )
    problems.extend(
        f"{relative} no longer exists, so remove its entry from the baseline."
        for relative in sorted(baseline)
        if relative not in sizes
    )
    return problems


def test_file_size_check_applies_the_ratchet(tmp_path: Path) -> None:
    sizes = (
        ("clean.py", 3),
        ("new.py", 501),
        ("grown.py", 502),
        ("shrank.py", 520),
        ("shrunk.py", 500),
    )
    for name, lines in sizes:
        (tmp_path / name).write_text("x = 1\n" * lines, encoding="utf-8")
    baseline = {"grown.py": 501, "shrank.py": 530, "shrunk.py": 510, "gone.py": 600}
    problems = _file_size_problems(tmp_path, [name for name, _ in sizes], baseline)
    assert [problem.split(" ")[0] for problem in problems] == [
        "grown.py",
        "new.py",
        "shrank.py",
        "shrunk.py",
        "gone.py",
    ]
    assert "responsibility seam" in problems[0]
    assert "Lower its count in the baseline to 520" in problems[2]
    assert "remove its entry" in problems[3]
    assert _file_size_problems(tmp_path, ("clean.py",), {}) == []
    held = {"grown.py": 502, "new.py": 501}
    assert _file_size_problems(tmp_path, ("grown.py", "new.py"), held) == []


def test_size_ratchet_stops_a_new_long_test_and_a_grown_script(tmp_path: Path) -> None:
    names = ("test_new.py", "flow.js")
    assert is_size_limited("tests/test_new.py")
    assert is_size_limited("studio/src/explorer.ts")
    assert is_size_limited("fixtures/capture_typescript_config_reference.cjs")
    (tmp_path / "test_new.py").write_text("x = 1\n" * 501, encoding="utf-8")
    (tmp_path / "flow.js").write_text("let x;\n" * 3603, encoding="utf-8")
    problems = _file_size_problems(tmp_path, names, {"flow.js": 3602})
    assert [problem.split(" ")[0] for problem in problems] == ["flow.js", "test_new.py"]
    assert "grew past 3602" in problems[0]


def test_file_size_limit_covers_code_and_not_data() -> None:
    assert is_size_limited("src/archkeel/cli/__init__.py")
    assert is_size_limited("native/ts/src/lib.rs")
    assert is_size_limited("crates/py/src/lib.rs")
    assert is_size_limited("native/report/assets/explorer/report-layout.js")
    assert is_size_limited("native/report/assets/report.css")
    assert not is_size_limited("native/report/assets/Geist-Variable.woff2")
    assert is_size_limited("tests/test_analyzer.py")
    assert is_size_limited("fixtures/demo_catalog_types.py")
    assert is_size_limited("tools/self_check_gate.py")
    assert is_size_limited("fixtures/capture_typescript_config_reference.cjs")
    assert not is_size_limited("tools/browser-runtime/node_modules/x/index.js")
    assert not is_size_limited("fixtures/H-typescript/src/main.ts")
    assert not is_size_limited("tests/golden/typescript/expected.json")
    assert not is_size_limited("tests/golden/typescript/sources/a/src/b.py")
    for relative in SIZE_LIMIT_EXEMPT:
        assert not is_size_limited(relative)


def test_source_files_stay_within_the_size_limit() -> None:
    """AD-314: a file over the limit is listed with its size, and the list only shrinks.

    Lines are counted with `splitlines()`, so U+2028 and other Unicode breaks count as breaks.
    """
    baseline = json.loads(FILE_SIZE_BASELINE.read_text(encoding="utf-8"))
    relatives = [
        relative
        for path in TRACKED
        if is_size_limited(relative := path.relative_to(ROOT).as_posix())
    ]
    assert relatives
    problems = _file_size_problems(ROOT, relatives, baseline)
    assert problems == [], "\n".join(
        ("Fix each file below. Never raise a number in tests/file_size_baseline.json.", *problems)
    )


def test_long_functions_have_a_named_reason() -> None:
    # AD-6: every long function is listed with its reason, and the list only shrinks.
    long_functions = {
        f"{path.relative_to(ROOT)}::{name}"
        for path in SOURCES
        for name, lines in _functions(ast.parse(path.read_bytes()), "")
        if lines > LONG_FUNCTION_LINES
    }
    assert sorted(long_functions - ALLOWED_LONG_FUNCTIONS.keys()) == []
    assert sorted(ALLOWED_LONG_FUNCTIONS.keys() - long_functions) == []


def test_sdist_ships_library_and_build_inputs_only() -> None:
    """The sdist promises a runnable test suite only if it ships one that can run.

    It cannot: a tarball has no `.git` for the license-header check above, no pinned
    interpreters for `fixtures/E-runtime`, and none of the cross-test imports the suite relies on.
    A shipped-but-untestable suite would be a second, weaker definition of
    "tests pass," so `only-include` carries what rebuilds the wheel (`src`, `schema` and the
    declared `README.md`) and distributors rebuild the test suite from the Git tag instead
    (docs/reference.md).
    """
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    only_include = config["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    missing = [entry for entry in only_include if not (ROOT / entry).exists()]
    assert missing == [], f"only-include names a path the repository does not have: {missing}"

    def is_test_input(entry: str) -> bool:
        return entry.partition("/")[0] in {"tests", "fixtures", "tools"}

    studio_build_inputs = {
        "tools/studio_ui.py",
        "tools/browser-runtime/package.json",
        "tools/browser-runtime/package-lock.json",
    }
    assert studio_build_inputs | {"studio"} <= set(only_include)
    shipped_test_inputs = [
        entry for entry in only_include if is_test_input(entry) and entry not in studio_build_inputs
    ]
    assert shipped_test_inputs == [], (
        "the sdist must not ship a test suite or its fixtures: it cannot run from a tarball "
        f"(see docs/reference.md), so shipping it half-working is worse than not shipping it; "
        f"found {shipped_test_inputs}"
    )


DECISION_LINE_LIMIT = 70


def test_decision_records_stay_readable() -> None:
    """AD-19: decisions stay short enough to review, without historical exceptions."""
    decisions = sorted((ROOT / "docs/architecture/decisions").glob("ad-*.md"))
    assert decisions, "no decision records found"
    too_long = {
        path.name for path in decisions if len(path.read_text().splitlines()) > DECISION_LINE_LIMIT
    }
    assert sorted(too_long) == [], f"decision records must stay within {DECISION_LINE_LIMIT} lines"
