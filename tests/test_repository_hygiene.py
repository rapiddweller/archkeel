# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import ast
import subprocess
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
    "src/archkeel/check/expectation.py::evaluate_expectation": "Raises in declaration order; each "
    "step reads the previous index.",
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
