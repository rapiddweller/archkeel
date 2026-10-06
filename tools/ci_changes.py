"""Classify changed paths into the CI capabilities they need."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class Areas:
    core: bool = False
    report: bool = False
    mermaid: bool = False


ALL_AREAS = Areas(core=True, report=True, mermaid=True)
_SCREENSHOT_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}
_SCREENSHOT_ROOTS = ("docs/assets/", "docs/evidence/")
_REPORT_PATTERNS = (
    "src/archkeel/render/*",
    "src/archkeel/check/report.py",
    "src/archkeel/check/uml*.py",
    "docs/report-visual-system.md",
    "tools/report_*.py",
    "tools/terminal_svg.py",
    "fixtures/architecture_demo.py",
    "fixtures/demo_catalog_*.py",
    "tests/*report*.py",
    "tests/*uml*.py",
    "tests/*flow*.py",
    "tests/test_secondary_table_acceptance.py",
    "tests/test_legacy_graph_rendering.py",
    "tests/test_diff_import_rendering.py",
    "tests/browser_report_support.py",
    "tests/graph_report_support.py",
)
_PRODUCT_MARKDOWN_ROOTS = (
    ".agents/",
    ".claude-plugin/",
    "fixtures/",
    "packages/",
    "plugins/",
    "skills/",
    "src/",
    "tests/",
    "tools/",
)
_DOC_MARKDOWN_FILES = {
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "README.md",
    "RELEASE_NOTES.md",
    "docs/README.md",
    "docs/known-limits.md",
    "docs/review-pilot.md",
    "docs/roadmap.md",
    "docs/target-first.md",
}
_CORE_MARKDOWN_FILES = {
    "README.md",
    "docs/architecture-demo.md",
    "docs/onboarding.md",
    "docs/reference.md",
    "docs/rule-yield.md",
    "docs/rules.md",
}


def _is_ci_path(path: str) -> bool:
    name = PurePosixPath(path).name
    return (
        name == "Makefile"
        or path.startswith(".github/workflows/")
        or path.startswith(".github/actions/")
    )


def classify_path(path: str) -> Areas:
    """Return all CI areas required to validate one repository-relative path."""
    if _is_ci_path(path):
        return ALL_AREAS

    if any(fnmatchcase(path, pattern) for pattern in _REPORT_PATTERNS):
        return Areas(core=True, report=True, mermaid=path.endswith(".md"))

    suffix = PurePosixPath(path).suffix.lower()
    if suffix in _SCREENSHOT_SUFFIXES and path.startswith(_SCREENSHOT_ROOTS):
        return Areas()

    if path in {"tools/mermaid_blocks.py", "tests/test_mermaid.py"}:
        return Areas(core=True, mermaid=True)

    if suffix == ".md":
        core_markdown = (
            path.startswith((*_PRODUCT_MARKDOWN_ROOTS, "docs/architecture/"))
            or path in _CORE_MARKDOWN_FILES
        )
        known_docs = path in _DOC_MARKDOWN_FILES or path.startswith("docs/evidence/")
        return Areas(core=core_markdown or not known_docs, mermaid=True)

    # Unknown paths fail closed so new product or configuration files keep the gate.
    return Areas(core=True)


def classify_paths(paths: Iterable[str]) -> Areas:
    core = report = mermaid = False
    found_path = False
    for path in paths:
        found_path = True
        areas = classify_path(path)
        core |= areas.core
        report |= areas.report
        mermaid |= areas.mermaid
    if not found_path:
        core = True
    return Areas(core=core, report=report, mermaid=mermaid)


def _write(areas: Areas) -> None:
    print(f"core={str(areas.core).lower()}")
    print(f"report={str(areas.report).lower()}")
    print(f"mermaid={str(areas.mermaid).lower()}")


def main() -> int:
    if sys.argv[1:] == ["--all"]:
        _write(ALL_AREAS)
        return 0
    if sys.argv[1:]:
        print("usage: ci_changes.py [--all]", file=sys.stderr)
        return 2
    paths = (os.fsdecode(path) for path in sys.stdin.buffer.read().split(b"\0") if path)
    _write(classify_paths(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
