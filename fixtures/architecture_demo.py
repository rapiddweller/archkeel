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
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from archkeel.cli import html_path
from archkeel.cli import main as archkeel_main
from archkeel.ir.graph_codec import parse_report
from fixtures.demo_catalog_check import VARIANTS as _CHECK_PROTOCOL_VARIANTS
from fixtures.demo_catalog_check_regressions import VARIANTS as _CHECK_REGRESSION_VARIANTS
from fixtures.demo_catalog_compass import VARIANTS as _COMPASS_VARIANTS
from fixtures.demo_catalog_compatibility import VARIANTS as _COMPATIBILITY_VARIANTS
from fixtures.demo_catalog_constructs import VARIANTS as _CONSTRUCT_VARIANTS
from fixtures.demo_catalog_dart import VARIANTS as _DART_VARIANTS
from fixtures.demo_catalog_dependencies import VARIANTS as _DEPENDENCY_VARIANTS
from fixtures.demo_catalog_evidence import VARIANTS as _EVIDENCE_VARIANTS
from fixtures.demo_catalog_exact_ownership import VARIANTS as _EXACT_OWNERSHIP_VARIANTS
from fixtures.demo_catalog_flutter import FLUTTER_FIXTURE_DIR
from fixtures.demo_catalog_flutter import VARIANTS as _FLUTTER_VARIANTS
from fixtures.demo_catalog_interfaces import VARIANTS as _INTERFACE_VARIANTS
from fixtures.demo_catalog_layout import VARIANTS as _LAYOUT_VARIANTS
from fixtures.demo_catalog_python_realworld import VARIANTS as _PYTHON_REALWORLD_VARIANTS
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
    *_FLUTTER_VARIANTS,
    *_COMPASS_VARIANTS,
    *_PYTHON_REALWORLD_VARIANTS,
)


REPORT_CASES = {
    "uml-match": ("uml-match", 0),
    "uml-complete": ("uml-complete", 0),
    "uml-dart-match": ("uml-dart-match", 0),
    "uml-dart-signature-fail": ("uml-dart-signature-fail", 2),
    "uml-dart-missing-member-fail": ("uml-dart-missing-member-fail", 2),
    "uml-dart-forbidden-dependency-fail": ("uml-dart-forbidden-dependency-fail", 2),
    "uml-dart-partial-unknown": ("uml-dart-partial-unknown", 0),
    "uml-flutter-shop": ("flutter-shop", 0),
    "uml-flutter-signature-fail": ("flutter-signature-fail", 2),
    "uml-flutter-missing-member-fail": ("flutter-missing-member-fail", 2),
    "uml-flutter-forbidden-dependency-fail": ("flutter-forbidden-dependency-fail", 2),
    "uml-flutter-dynamic-unknown": ("flutter-dynamic-unknown", 0),
    "uml-flutter-unsupported-declaration": ("flutter-unsupported-declaration", 2),
    "uml-compass-project": ("compass-project", 2),
    "uml-compass-forbidden-edge": ("compass-forbidden-edge", 2),
    "uml-compass-signature-fail": ("compass-signature-fail", 2),
    "uml-compass-dynamic-unknown": ("compass-dynamic-unknown", 2),
    "uml-python-realworld-project": ("python-realworld-project", 2),
    "uml-python-realworld-forbidden-edge": ("python-realworld-forbidden-edge", 2),
    "uml-python-realworld-signature-fail": ("python-realworld-signature-fail", 2),
    "uml-python-realworld-dynamic-unknown": ("python-realworld-dynamic-unknown", 2),
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
    "empty-responsibility": ("target-empty-responsibilities", 2),
}
UML_DEMO_COMPARISONS = {
    "uml-match": "PASS",
    "uml-complete": "UNKNOWN",
    "uml-mismatch": "FAIL",
    "uml-partial": "UNKNOWN",
    "uml-dart-match": "PASS",
    "uml-dart-signature-fail": "FAIL",
    "uml-dart-missing-member-fail": "FAIL",
    "uml-dart-forbidden-dependency-fail": "PASS",
    "uml-dart-partial-unknown": "UNKNOWN",
    "uml-flutter-shop": "UNKNOWN",
    "uml-flutter-signature-fail": "FAIL",
    "uml-flutter-missing-member-fail": "FAIL",
    "uml-flutter-forbidden-dependency-fail": "UNKNOWN",
    "uml-flutter-dynamic-unknown": "UNKNOWN",
    "uml-flutter-unsupported-declaration": "UNKNOWN",
    "uml-compass-project": "UNKNOWN",
    "uml-compass-forbidden-edge": "UNKNOWN",
    "uml-compass-signature-fail": "FAIL",
    "uml-compass-dynamic-unknown": "FAIL",
    "uml-python-realworld-project": "UNKNOWN",
    "uml-python-realworld-forbidden-edge": "UNKNOWN",
    "uml-python-realworld-signature-fail": "FAIL",
    "uml-python-realworld-dynamic-unknown": "UNKNOWN",
    "uml-typescript": "UNKNOWN",
    "uml-typescript-match": "PASS",
    "uml-typescript-mismatch": "FAIL",
    "uml-typescript-partial": "UNKNOWN",
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

Dart has independent Target PASS, signature/member and dependency FAIL, and partial-resolution
UNKNOWN cases. TypeScript includes PASS, FAIL and UNKNOWN UML cases; unsupported or ambiguous
source facts stay UNKNOWN.

Flutter adds a nested shop journey with source-only signature, enum-member, dependency, dynamic,
and unsupported-declaration cases. The base keeps external framework and inferred-type facts
UNKNOWN rather than treating them as resolved relationships.

Python adds the complete pinned FastAPI RealWorld app (72 Python modules) with architecture,
deep field-signature, and login-call variants. Its source coverage is complete; external UML
facts remain UNKNOWN.

| Variant | Expected evidence |
|---|---|
| `flutter-shop` | Local comparison passes; unresolved source facts keep UML UNKNOWN. |
| `flutter-signature-fail` | `OrderLine.lineTotalCents` signature FAIL. |
| `flutter-missing-member-fail` | `OrderStatus.completed` existence FAIL. |
| `flutter-forbidden-dependency-fail` | `complete_requires` FAIL for presentation → data. |
| `flutter-dynamic-unknown` | Dynamic `watchAll` call remains UNKNOWN. |
| `flutter-unsupported-declaration` | Extension yields a coverage gap and UNKNOWN observation. |
| `python-realworld-forbidden-edge` | Route imports SQL directly; rule FAIL. |
| `python-realworld-signature-fail` | `Article.tags` changes to `List[int]`; UML FAIL. |
| `python-realworld-dynamic-unknown` | `getattr` login call; UNKNOWN. |

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
    mode.add_argument("--uml-suite", action="store_true", help="Replay all language UML cases.")
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
    if args.uml_suite:
        if args.output is None:
            parser.error("--uml-suite requires --output")
        try:
            return uml_suite(args.output)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            print(f"UML demo suite failed: {error}", file=sys.stderr)
            return 2
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


def uml_suite(output_dir: Path) -> int:
    """Run all UML cases and verify actual exits, report verdicts and artifacts."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, comparison_status in UML_DEMO_COMPARISONS.items():
        variant, expected_exit = REPORT_CASES[name]
        row = next(item for item in CATALOG if item.id == variant)
        output = output_dir / f"{name}.json"
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            actual_exit = replay(variant, output)
        if actual_exit != expected_exit:
            raise ValueError(f"{name}: exit {actual_exit}, expected {expected_exit}")
        summaries = [
            json.loads(line)
            for line in captured.getvalue().splitlines()
            if line.startswith("{") and line.endswith("}")
        ]
        if not summaries or summaries[-1].get("declared_rules") != row.expected_declared_rules:
            raise ValueError(f"{name}: report summary did not prove {row.expected_declared_rules}")
        if not output.is_file() or not output.with_suffix(".report.html").is_file():
            raise ValueError(f"{name}: report JSON and HTML must both be written")
        if variant == "flutter-unsupported-declaration":
            report_summary = next(item for item in summaries if item.get("command") == "report")
            failures = report_summary["coverage"]["failures"]
            if (
                report_summary["observation_complete"] != "UNKNOWN"
                or report_summary["coverage"]["status"] != "FAIL"
                or not any(item["kind"] == "UnsupportedDeclaration" for item in failures)
            ):
                raise ValueError(f"{name}: expected explicit unsupported-declaration coverage")
            print(
                f"{name}: exit={actual_exit} declared_rules={row.expected_declared_rules} "
                "uml=UNKNOWN (comparison unavailable because coverage is incomplete)"
            )
            continue
        report_html = output.with_suffix(".report.html")
        main = json.loads(_page_payload(report_html.read_text(encoding="utf-8")))
        detail = report_html.with_name(main["atlas"]["detail_page"])
        detail_payload = json.loads(_page_payload(detail.read_text(encoding="utf-8")))
        report = parse_report(
            {
                key: value
                for key, value in detail_payload.items()
                if key not in {"initial_scope", "initial_view", "navigation"}
            }
        )
        if report.comparison is None or report.comparison.status != comparison_status:
            raise ValueError(f"{name}: UML comparison status differs from {comparison_status}")
        print(
            f"{name}: exit={actual_exit} declared_rules={row.expected_declared_rules} "
            f"uml={comparison_status}"
        )
    return 0


def _page_payload(html: str) -> str:
    match = re.search(r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>', html, re.DOTALL)
    if match is None:
        raise ValueError("report HTML is missing its flow-data payload")
    return match.group(1)


@contextlib.contextmanager
def materialized_fixture(variant: Variant) -> Iterator[Path]:
    """Yield a clean-baseline demo tree with its catalog overlay applied."""
    with tempfile.TemporaryDirectory(prefix="archkeel-demo-") as temporary:
        root = Path(temporary) / variant.fixture.name
        ignored = (
            shutil.ignore_patterns(".dart_tool", "build")
            if variant.fixture.resolve() == FLUTTER_FIXTURE_DIR.resolve()
            else None
        )
        shutil.copytree(variant.fixture, root, ignore=ignored)
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
