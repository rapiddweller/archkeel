# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 architecture demo catalog: the single source read by the test and by markdown().

Every named `Variant` maps a copy of the clean `fixtures/F-architecture` shop sample to the
exact rule ids, `DiagnosticCode` and `DiagnosticKind` values `validate` and `report` must
produce. Rows that run on the sample apply file overlays; rows that compare two observations
or record a declaration Archkeel never enforces cite existing evidence instead.

Regenerate `docs/architecture-demo.md` from the repository root with:

    python -m fixtures.architecture_demo --markdown
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Iterator
from pathlib import Path

from archkeel.cli import html_path
from archkeel.cli import main as archkeel_main
from archkeel.cli.config import CONFIG_PATH
from fixtures.demo_catalog_check import VARIANTS as _CHECK_PROTOCOL_VARIANTS
from fixtures.demo_catalog_check_regressions import VARIANTS as _CHECK_REGRESSION_VARIANTS
from fixtures.demo_catalog_compatibility import VARIANTS as _COMPATIBILITY_VARIANTS
from fixtures.demo_catalog_constructs import VARIANTS as _CONSTRUCT_VARIANTS
from fixtures.demo_catalog_dart import VARIANTS as _DART_VARIANTS
from fixtures.demo_catalog_dependencies import VARIANTS as _DEPENDENCY_VARIANTS
from fixtures.demo_catalog_evidence import VARIANTS as _EVIDENCE_VARIANTS
from fixtures.demo_catalog_interfaces import VARIANTS as _INTERFACE_VARIANTS
from fixtures.demo_catalog_layout import VARIANTS as _LAYOUT_VARIANTS
from fixtures.demo_catalog_showcase import VARIANTS as _SHOWCASE_VARIANTS
from fixtures.demo_catalog_support import FIXTURE_DIR, Variant, apply_overlay
from fixtures.demo_catalog_test_scope import VARIANTS as _TEST_SCOPE_VARIANTS
from fixtures.demo_catalog_types import VARIANTS as _TYPE_VARIANTS
from fixtures.demo_catalog_validation import VARIANTS as _VALIDATION_VARIANTS
from fixtures.demo_catalog_widening import VARIANTS as _WIDENING_VARIANTS

CATALOG: tuple[Variant, ...] = (
    *_SHOWCASE_VARIANTS,
    *_COMPATIBILITY_VARIANTS,
    *_CONSTRUCT_VARIANTS,
    *_DEPENDENCY_VARIANTS,
    *_INTERFACE_VARIANTS,
    *_LAYOUT_VARIANTS,
    *_TEST_SCOPE_VARIANTS,
    *_TYPE_VARIANTS,
    *_VALIDATION_VARIANTS,
    *_WIDENING_VARIANTS,
    *_CHECK_PROTOCOL_VARIANTS,
    *_CHECK_REGRESSION_VARIANTS,
    *_EVIDENCE_VARIANTS,
    *_DART_VARIANTS,
)

_INTRO = (
    "Generated from `fixtures/architecture_demo.py`'s `CATALOG`. Every checkable item in the "
    "decision records under `docs/architecture/decisions/` (indexed by "
    "`docs/architecture/archkeel.md`, AD-11) has one row below: a named variant, the "
    "rule ids and diagnostic codes (AD-12) it must produce, and either the shop sample "
    "files it changes or the existing evidence that demonstrates it instead. Regenerate "
    "with `python -m fixtures.architecture_demo --markdown`."
)
_SHOWCASE_NOTE = (
    "The `showcase` row below (`tour`) is the default demo view: it applies many overlays "
    "at once so one run shows many violations together; every other row isolates one item."
)
_REPLAY_NOTE = (
    "Replay a report-capable row with `python -m fixtures.architecture_demo --replay <variant> "
    "--output <new-path>`; it emits a `validate` result, then writes the ordinary report JSON and "
    "HTML sidecar. Report generation is always attempted; the command exit is the higher of "
    "validation and report exits. A failed validation does not suppress a report whose own "
    "inputs are valid; an invalid explicit baseline also rejects the report. "
    "Baseline flags are used only when "
    "the row declares one, and a declared baseline is passed to both commands; only "
    "`deepest_inside_changed` replays its `--against` history. "
    "Check-protocol and tested-only rows are excluded. "
    "The destination files must not exist. `make demo-architecture VARIANT=<variant> "
    "OUTPUT=<new-path>` delegates to the same command."
)
_DART_NOTE = (
    "Rows whose item starts with `dart:` run on `fixtures/G-dart`, a Flutter-style package "
    'scanned with `language = "dart"` (AD-97); `dart-tour` is their showcase. Replay them '
    "as one story with `make demo-dart`."
)
_TARGET_HIERARCHY_NOTE = (
    "Target hierarchy rows exercise declared physical frames, missing and ambiguous placement, "
    "and requirement cycles. Frames describe layout, not semantic ownership. Placement is "
    "`declared`, `inferred`, `multiple`, `ambiguous` or `unmapped`; exact `public` and "
    "`requires.through` remain declaration details. A null dependency rank can mean a cycle or a "
    "dependent of one, so it does not name an SCC or change the architecture verdict. Browser "
    "acceptance checks 100% initial zoom, native scrolling, collapsed Details, and selection "
    "identity across Actual, Target and Diff. The CE preview was accepted on 1 October; the "
    "report does not certify CE completion."
)
_BROWSER_NOTE = (
    "`make report-browser OUTPUT=<fresh-directory>` captures the current README views. The "
    "independent browser tests also cover a native dragged no-route case: selected Details "
    "exposes a separate layout warning without changing architecture data. "
    "The `tour` capture exercises tight focused rows: choose `app` and `Violating edges only`. "
    "All seven violating edges retain selectable labels; labels moved beside the graph name "
    "their source and target. The clean root and nested `store` captures exercise the "
    "conforming case."
)


def _demo_type(variant: Variant) -> str:
    """Name each row's demo kind: what it runs, not what it changes."""
    if variant.check is not None:
        return "check run"
    if variant.against is not None:
        return "validate --against run"
    if variant.evidence is not None:
        return "tested only"
    if variant.write_baseline:
        return "validate --write-baseline run"
    if variant.config != CONFIG_PATH:
        return f"validate/report --config {variant.config} run"
    return "validate/report run"


def markdown() -> str:
    """Render docs/architecture-demo.md from CATALOG."""
    lines = [
        "# Architecture demo catalog",
        "",
        *textwrap.wrap(_INTRO, width=100, break_long_words=False, break_on_hyphens=False),
        "",
        *textwrap.wrap(_SHOWCASE_NOTE, width=100, break_long_words=False, break_on_hyphens=False),
        "",
        *textwrap.wrap(_REPLAY_NOTE, width=100, break_long_words=False, break_on_hyphens=False),
        "",
        *textwrap.wrap(_DART_NOTE, width=100, break_long_words=False, break_on_hyphens=False),
        "",
        *textwrap.wrap(
            _TARGET_HIERARCHY_NOTE, width=100, break_long_words=False, break_on_hyphens=False
        ),
        "",
        *textwrap.wrap(_BROWSER_NOTE, width=100, break_long_words=False, break_on_hyphens=False),
        "",
        "| Section | Item | Variant | Demo | Rule ids | Diagnostic codes | Evidence / files |",
        "|---|---|---|---|---|---|---|",
    ]
    for variant in CATALOG:
        violations = ", ".join(variant.expected_violations) or "-"
        codes = ", ".join(variant.expected_codes) or "-"
        # A row on another sample names it, so its file paths are not read as the shop's.
        sample = "" if variant.fixture == FIXTURE_DIR else f"{variant.fixture.name}: "
        reference = variant.evidence or sample + (
            ", ".join(sorted(variant.files)) or "clean sample"
        )
        lines.append(
            f"| {variant.section} | {variant.item} | {variant.id} | {_demo_type(variant)} | "
            f"{violations} | {codes} | {reference} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--markdown", action="store_true")
    mode.add_argument("--replay", metavar="VARIANT", help="Replay one catalog variant.")
    parser.add_argument(
        "--output", type=Path, help="New report JSON path; HTML is written beside it."
    )
    args = parser.parse_args(argv)
    if args.markdown:
        if args.output is not None:
            parser.error("--output is only valid with --replay")
        text = markdown()
        (Path(__file__).resolve().parent.parent / "docs/architecture-demo.md").write_text(text)
        print(text)
        return 0
    if args.output is None:
        parser.error("--replay requires --output")
    try:
        return replay(args.replay, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"architecture demo replay failed: {error}", file=sys.stderr)
        return 2


def replay(variant_id: str, output: Path) -> int:
    """Replay one sample overlay with the ordinary report command into new files."""
    variant = next((item for item in CATALOG if item.id == variant_id), None)
    if variant is None:
        raise ValueError(f"unknown catalog variant: {variant_id}")
    if variant.evidence is not None:
        raise ValueError(f"{variant_id} cites evidence and has no runnable fixture")
    if variant.check is not None:
        raise ValueError(f"{variant_id} is a check-protocol row, not a report-capable variant")
    if variant.against is not None and (
        variant.against.scenario != "deepest_inside_changed" or variant.against.root != "."
    ):
        raise ValueError(f"{variant_id} uses an unsupported --against scenario")

    output = output.resolve()
    report_html = html_path(output, "report")
    if output == report_html:
        raise ValueError("JSON and HTML output paths collide")
    output.parent.mkdir(parents=True, exist_ok=True)
    reserved: list[Path] = []
    try:
        for path in (output, report_html):
            with path.open("xb"):
                reserved.append(path)
        with materialized_fixture(variant) as root:
            validate = ["validate", "--root", str(root), "--config", variant.config]
            if variant.baseline is not None:
                validate.extend(("--baseline", variant.baseline))
            if variant.write_baseline:
                validate.append("--write-baseline")
            if variant.against is not None:
                validate.extend(("--against", "main"))
            validate_exit_code = archkeel_main([*validate, "--json"])
            report = [
                "report",
                "--root",
                str(root),
                "--config",
                variant.config,
                "--output",
                str(output),
            ]
            if variant.baseline is not None:
                report.extend(("--baseline", variant.baseline))
            report_exit_code = archkeel_main([*report, "--json"])
            for path in reserved:
                if path.is_file() and path.stat().st_size == 0:
                    path.unlink()
            return max(validate_exit_code, report_exit_code)
    except Exception:
        for path in reserved:
            if path.is_file() and path.stat().st_size == 0:
                path.unlink()
        raise


@contextlib.contextmanager
def materialized_fixture(variant: Variant) -> Iterator[Path]:
    """Yield a clean-baseline demo tree with its catalog overlay applied."""
    with tempfile.TemporaryDirectory(prefix="archkeel-demo-") as temporary:
        root = Path(temporary) / variant.fixture.name
        shutil.copytree(variant.fixture, root)
        if variant.against is not None:
            apply_overlay(root, variant.against.base_files)
        for command in (
            ("init", "-q", "-b", "main"),
            ("config", "user.email", "demo@example.invalid"),
            ("config", "user.name", "Demo"),
            ("add", "-A"),
            ("-c", "commit.gpgsign=false", "commit", "-q", "-m", variant.id),
        ):
            subprocess.run(["git", *command], cwd=root, check=True, capture_output=True)
        apply_overlay(root, variant.files)
        yield root


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
