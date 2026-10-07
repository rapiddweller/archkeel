# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 demo variants and their generated replay guide.

CATALOG owns fixture overlays and expected validate/report outcomes.
Regenerate docs/architecture-demo.md with --markdown.
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from archkeel.cli import html_path
from archkeel.cli import main as archkeel_main
from fixtures.demo_catalog_check import VARIANTS as _CHECK_PROTOCOL_VARIANTS
from fixtures.demo_catalog_check_regressions import VARIANTS as _CHECK_REGRESSION_VARIANTS
from fixtures.demo_catalog_compatibility import VARIANTS as _COMPATIBILITY_VARIANTS
from fixtures.demo_catalog_constructs import VARIANTS as _CONSTRUCT_VARIANTS
from fixtures.demo_catalog_dart import VARIANTS as _DART_VARIANTS
from fixtures.demo_catalog_dependencies import VARIANTS as _DEPENDENCY_VARIANTS
from fixtures.demo_catalog_evidence import VARIANTS as _EVIDENCE_VARIANTS
from fixtures.demo_catalog_exact_ownership import VARIANTS as _EXACT_OWNERSHIP_VARIANTS
from fixtures.demo_catalog_interfaces import VARIANTS as _INTERFACE_VARIANTS
from fixtures.demo_catalog_layout import VARIANTS as _LAYOUT_VARIANTS
from fixtures.demo_catalog_showcase import VARIANTS as _SHOWCASE_VARIANTS
from fixtures.demo_catalog_support import Variant, apply_overlay
from fixtures.demo_catalog_test_scope import VARIANTS as _TEST_SCOPE_VARIANTS
from fixtures.demo_catalog_types import VARIANTS as _TYPE_VARIANTS
from fixtures.demo_catalog_uml import VARIANTS as _UML_VARIANTS
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
    *_UML_VARIANTS,
    *_EXACT_OWNERSHIP_VARIANTS,
    *_DART_VARIANTS,
)


REPORT_CASES = {
    "uml-match": ("uml-match", 0),
    "uml-complete": ("uml-complete", 0),
    "uml-dart": ("uml-dart", 0),
    "uml-typescript": ("uml-typescript", 0),
    "uml-typescript-match": ("uml-typescript-match", 0),
    "uml-typescript-mismatch": ("uml-typescript-mismatch", 2),
    "uml-typescript-partial": ("uml-typescript-partial", 0),
    "uml-mismatch": ("uml-mismatch", 2),
    "uml-partial": ("uml-partial", 0),
    "tour": ("tour", 2),
    "clean": ("clean", 0),
    "open": ("class-a-decision-open", 2),
    "wide": ("class-a-recursive-wide-package", 0),
    "deep": ("class-a-recursive-inside-violation", 2),
    "mixed": ("class-a-boundary-types-mixed-evidence", 2),
    "unknown": ("class-a-boundary-types-ordinary-reexport-chain-unknown", 0),
    "known": ("validation-baseline-subject-order", 0),
    "target-present": ("target-module-present", 0),
    "target-absent": ("target-module-absent", 0),
    "target-store": ("target-hierarchy-positive", 0),
    "empty-responsibility": ("target-empty-responsibilities", 0),
}


def markdown() -> str:
    """Generate the short demo guide; CATALOG owns the complete case inventory."""
    return """# Architecture demos

Create a report with several deliberate violations:

```sh
make demo-architecture VARIANT=tour OUTPUT=build/demo.json
```

Use a new output path. The command validates, then writes report JSON and HTML.
Its exit is the higher validation/report exit; read the report's verdict separately.

For Python, Dart and TypeScript UML examples:

```sh
make demo-uml OUTPUT=build/uml-demo
```

Dart inner observation remains unavailable. TypeScript includes PASS, FAIL and UNKNOWN UML cases;
unsupported or ambiguous source facts stay UNKNOWN.

The [catalog](../fixtures/architecture_demo.py) owns all variants, overlays and expected
outcomes. Check-protocol and test-only variants cannot replay as reports.
[Tests](../tests/test_architecture_demo.py) verify the catalog; the guide omits its full inventory.

Regenerate this page: `uv run --locked python -m fixtures.architecture_demo --markdown`.
"""


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
