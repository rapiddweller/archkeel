# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import ast
import json
import re
import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).parents[1]
HEADER = "\n".join(
    (
        "# Archkeel",
        "# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.",
        "# SPDX-License-Identifier: MIT",
        "",
    )
).encode()
FORBIDDEN = (
    b"/" + b"Users/",
    b"/" + b"home/",
    b"/" + b"private/tmp",
    b"/" + b"tmp/",
    b"/" + b"var/folders",
    b"C:" + bytes([92]),
)
# Split so this file does not match itself. A lone `=======` is a Markdown setext heading, so
# only the two unambiguous markers count; a conflict always leaves at least one of them.
CONFLICT_MARKERS = (b"<<<" + b"<<<<", b">>>" + b">>>>")
TRACKED = tuple(
    ROOT / name
    for name in subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True).split("\0")
    if name
)
SOURCES = tuple(
    path for path in TRACKED if path.suffix == ".py" and path.is_relative_to(ROOT / "src")
)
LONG_FUNCTION_LINES = 80
ALLOWED_LONG_FUNCTIONS = {
    "src/archkeel/analyzer/__init__.py::observe": "Subprocess boundary; one try maps launch, "
    "decode and failure to diagnostics.",
    "src/archkeel/analyzer/embedded/contexts.py::_access_observations": "One ast.walk records "
    "bindings while it scans accesses; separate passes would change which reads count.",
    "src/archkeel/analyzer/embedded/contexts.py::_class_fields": "One walk per method body "
    "threads fields, properties, post-init assignments and mutations together.",
    "src/archkeel/analyzer/embedded/contract.py::_rule_declaration": "One classified record per "
    "rule kind; the branches share nothing but the envelope below them.",
    "src/archkeel/analyzer/embedded/contract.py::project_declarations": "One classified record "
    "per declaration kind; nothing is shared between them.",
    "src/archkeel/analyzer/embedded/report.py::_metrics": "One literal of metric records; the "
    "sets above it only feed that literal.",
    "src/archkeel/analyzer/embedded/scanner.py::scan_repository": "Sequences the collectors into "
    "ScanResult; the remaining lines are collector calls and result fields.",
    "src/archkeel/check/delta.py::_compare_records": "Exact, relocated and changed stages share "
    "the unmatched record pools.",
    "src/archkeel/check/delta.py::build_architecture_delta": "Shared, coverage and availability "
    "reasons are decided in one place per dimension.",
    "src/archkeel/check/run.py::run_check": "Sequences authentication, git and host order, both "
    "snapshots and evaluation; one with-block owns the snapshot lifetimes.",
    "src/archkeel/cli/__init__.py::build_parser": "Declarative argparse setup, one subparser per "
    "command; help text is the length.",
    "src/archkeel/cli/__init__.py::main": "Composition root; one error boundary maps every "
    "command to a result.",
    "src/archkeel/ir/codec.py::encode_canonical_model": "Columnizing and interning share the "
    "sentinel rows.",
    "src/archkeel/ir/codec.py::parse_contract": "Field lists plus one parser per kind; the "
    "duplicate-id check spans all groups.",
    "src/archkeel/ir/codec.py::parse_delta": "Checks the delta envelope in wire order and "
    "assembles five named part parsers into one value.",
    "src/archkeel/render/html.py::render_html": "One template with its bindings.",
}


# A `git add -A` after running `archkeel report` to measure something committed `r.json`,
# `r.report.html` and two more into the repository root, and every test still passed. The root
# is small and changes rarely, so naming its whole contents catches any stray file rather than
# the report shapes that happened to land this time.
ROOT_FILES = frozenset(
    (
        ".gitignore",
        ".python-version",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "Makefile",
        "README.md",
        "RELEASE_NOTES.md",
        "architecture-contract.json",
        "archkeel.toml",
        "pyproject.toml",
        "uv.lock",
    )
)


def _functions(node: ast.AST, prefix: str) -> Iterator[tuple[str, int]]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            name = f"{prefix}{child.name}"
            if not isinstance(child, ast.ClassDef):
                yield name, (child.end_lineno or child.lineno) - child.lineno + 1
            yield from _functions(child, f"{name}.")
        else:
            yield from _functions(child, prefix)


def test_tracked_python_files_have_license_header() -> None:
    assert TRACKED
    missing = [
        str(path.relative_to(ROOT))
        for path in TRACKED
        if path.suffix == ".py" and not path.read_bytes().startswith(HEADER)
    ]
    assert missing == []


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


def test_every_analyzer_collector_is_a_declared_peer() -> None:
    """AD-25: a peer the contract never names is a peer nothing isolates.

    One-directional by design: every module defining a `collect_*` entry point must be
    declared, while a declared member need not follow that naming — `violations` exposes
    `rule_violations`. The second assertion catches a member left behind by a rename.
    """
    contract = json.loads((ROOT / "architecture-contract.json").read_bytes())
    declared = {
        member
        for rule in contract["rules"]
        if rule["kind"] == "sibling_isolation"
        for member in rule["members"]
    }
    collectors = {
        f"archkeel.analyzer.embedded.{path.stem}"
        for path in (ROOT / "src/archkeel/analyzer/embedded").glob("*.py")
        if any(
            isinstance(node, ast.FunctionDef) and node.name.startswith("collect_")
            for node in ast.parse(path.read_bytes()).body
        )
    }

    assert sorted(collectors - declared) == []
    assert [
        member
        for member in sorted(declared)
        if not (ROOT / f"src/{member.replace('.', '/')}.py").is_file()
    ] == []


def test_sdist_ships_library_and_build_inputs_only() -> None:
    """The sdist promises a runnable test suite only if it ships one that can run.

    It cannot: a tarball has no `.git` for the license-header check above, no pinned
    interpreters for `fixtures/E-runtime`, no `tools/`, and none of the cross-test imports the
    suite relies on. A shipped-but-untestable suite would be a second, weaker definition of
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

    shipped_test_inputs = [entry for entry in only_include if is_test_input(entry)]
    assert shipped_test_inputs == [], (
        "the sdist must not ship a test suite or its fixtures: it cannot run from a tarball "
        f"(see docs/reference.md), so shipping it half-working is worse than not shipping it; "
        f"found {shipped_test_inputs}"
    )


def test_decision_index_matches_decision_files() -> None:
    """AD-55: the decisions index and docs/architecture/decisions/ name the same set.

    A decision file nobody indexed, or an index row pointing at a missing file, is a
    drift the split's whole point was to prevent: add the file's row to the index table
    in docs/architecture/archkeel.md, or add the missing file under decisions/.
    """
    archkeel_md = (ROOT / "docs/architecture/archkeel.md").read_text(encoding="utf-8")
    indexed = dict(
        re.findall(
            r"^\| AD-(\S+) \| \[.*?\]\(decisions/(ad-\S+\.md)\) \|$", archkeel_md, re.MULTILINE
        )
    )
    decisions_dir = ROOT / "docs/architecture/decisions"
    on_disk = {path.name for path in decisions_dir.glob("ad-*.md")}

    assert indexed, "the index table in docs/architecture/archkeel.md parsed no rows"
    missing_files = sorted(set(indexed.values()) - on_disk)
    assert missing_files == [], (
        "the index in docs/architecture/archkeel.md names a file docs/architecture/decisions/ "
        f"does not have: {missing_files}"
    )
    unindexed_files = sorted(on_disk - set(indexed.values()))
    assert unindexed_files == [], (
        "docs/architecture/decisions/ holds a file the index in docs/architecture/archkeel.md "
        f"does not name: {unindexed_files}"
    )


def test_repository_root_holds_no_stray_file() -> None:
    """Generated output is invisible to every other guard: it is valid text at a plausible path."""
    tracked = frozenset(path.name for path in TRACKED if path.parent == ROOT)
    assert sorted(tracked - ROOT_FILES) == []
    assert sorted(ROOT_FILES - tracked) == []


def test_tracked_text_has_no_local_absolute_paths() -> None:
    hits = []
    for path in TRACKED:
        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        for line, text in enumerate(payload.splitlines(), 1):
            if any(prefix in text for prefix in FORBIDDEN):
                hits.append(f"{path.relative_to(ROOT)}:{line}")
    assert hits == []


def test_tracked_text_carries_no_unresolved_merge_conflict() -> None:
    """A `git add -A` over an unresolved merge commits the markers and every test still passes.

    That happened: a merge left them in the decision record, and the split carried them into a
    decision's own file, where nothing looked at them again.
    """
    hits = []
    for path in TRACKED:
        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        for line, text in enumerate(payload.splitlines(), 1):
            if any(text.startswith(marker) for marker in CONFLICT_MARKERS):
                hits.append(f"{path.relative_to(ROOT)}:{line}")
    assert hits == [], f"unresolved merge conflict markers: {hits}"
