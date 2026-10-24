# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Routing rules for the lightweight CI change classifier."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

from tools.ci_changes import Areas, classify_path, classify_paths


class ChangeClassificationTests(unittest.TestCase):
    def test_path_capabilities(self) -> None:
        cases = (
            ("src/archkeel/check/report.py", Areas(core=True, report=True)),
            ("src/archkeel/render/html.py", Areas(core=True, report=True)),
            ("tools/browser_runtime.py", Areas(core=True, report=True)),
            ("tools/browser-runtime/options.json", Areas(core=True, report=True)),
            ("tools/browser-runtime/package-lock.json", Areas(core=True, report=True)),
            ("tests/browser_runtime_ast.cjs", Areas(core=True, report=True)),
            ("tools/browser_graph_protocol.py", Areas(core=True, report=True)),
            ("src/archkeel/ir/architecture_graph.py", Areas(core=True, report=True)),
            ("src/archkeel/ir/facts.py", Areas(core=True, report=True)),
            ("tests/test_graph_scene_protocol.py", Areas(core=True, report=True)),
            ("tests/test_atlas_deviation_boundary.py", Areas(core=True, report=True)),
            ("tests/browser_graph_scene_target.ts", Areas(core=True, report=True)),
            ("fixtures/J-compass/lib/domain/use_cases/booking.dart", Areas(core=True, report=True)),
            ("fixtures/K-python-realworld/app/api/routes/users.py", Areas(core=True, report=True)),
            (
                "fixtures/L-nest-realworld/src/article/article.service.ts",
                Areas(core=True, report=True),
            ),
            (
                "src/archkeel/render/assets/archkeel-logo-dark.svg",
                Areas(core=True, report=True),
            ),
            (
                "src/archkeel/render/assets/archkeel-logo-light.svg",
                Areas(core=True, report=True),
            ),
            ("src/archkeel/render/assets/archkeel-mark.png", Areas(core=True, report=True)),
            ("Makefile", Areas(core=True, report=True, mermaid=True, full=True)),
            (".github/workflows/ci.yml", Areas(core=True, report=True, mermaid=True, full=True)),
            ("README.md", Areas(core=True, mermaid=True)),
            ("docs/architecture/archkeel.md", Areas(core=True, mermaid=True)),
            ("docs/architecture/decisions/README.md", Areas(core=True, mermaid=True)),
            ("docs/architecture-demo.md", Areas(core=True, mermaid=True)),
            ("docs/onboarding.md", Areas(core=True, mermaid=True)),
            ("docs/reference.md", Areas(core=True, mermaid=True)),
            ("docs/report-visual-system.md", Areas(core=True, report=True, mermaid=True)),
            ("docs/roadmap.md", Areas(mermaid=True)),
            ("skills/archkeel/SKILL.md", Areas(core=True, mermaid=True)),
            ("tools/mermaid_blocks.py", Areas(core=True, mermaid=True)),
            ("tests/test_mermaid.py", Areas(core=True, mermaid=True)),
            ("src/archkeel/check/analyzer.py", Areas(core=True)),
            ("unmapped/product/contract.yaml", Areas(core=True)),
            ("unmapped/notes.md", Areas(core=True, mermaid=True)),
            ("docs/assets/archkeel-report-preview.png", Areas()),
            ("docs/assets/archkeel-onboarding-loop.svg", Areas(core=True)),
            ("docs/assets/archkeel-shop-inside-violation.svg", Areas(core=True)),
            ("docs/assets/unlisted.png", Areas(core=True)),
            ("docs/evidence/internal-service/report-auto-flow.png", Areas(core=True)),
            ("assets/archkeel-mark.svg", Areas(core=True)),
            ("plugins/archkeel/assets/archkeel-mark.svg", Areas(core=True)),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(classify_path(path), expected)

    def test_areas_accumulate_across_paths(self) -> None:
        self.assertEqual(
            classify_paths(("README.md", "src/archkeel/render/html.py", "docs/shot.png")),
            Areas(core=True, report=True, mermaid=True),
        )

    def test_empty_diff_fails_closed(self) -> None:
        self.assertEqual(classify_paths(()), Areas(core=True))

    def test_verification_changes_require_full_acceptance(self) -> None:
        for path in (
            "Makefile",
            ".github/workflows/full-verification.yml",
            ".github/workflows/ci.yml",
            "tests/conftest.py",
            "tests/test_make_gate.py",
            "tests/test_ci_changes.py",
            "tools/ci_changes.py",
            "tools/report_timing.py",
            "tools/report_browser.py",
            "tools/report_pages.py",
            "tests/test_report_pages.py",
            "tests/test_report_browser.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(classify_path(path).full)
                self.assertTrue(classify_paths(("README.md", path)).full)

    def test_regular_product_and_docs_changes_keep_fast_checks(self) -> None:
        for path in ("src/archkeel/ir/model.py", "README.md", "docs/roadmap.md"):
            with self.subTest(path=path):
                self.assertFalse(classify_path(path).full)

    def test_main_runs_every_area_even_with_no_comparable_base(self) -> None:
        root = Path(__file__).parents[1]
        workflow = (root / ".github/workflows/ci.yml").read_text()
        step = workflow.split("      - name: Classify changed files\n", 1)[1].split(
            "\n  check:", 1
        )[0]
        self.assertIn("EVENT: ${{ github.event_name }}", step)
        script = dedent(step.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "outputs"
            run = subprocess.run(
                ["bash", "-eu", "-c", script],
                cwd=root,
                env={
                    **os.environ,
                    "EVENT": "push",
                    "BASE": "missing",
                    "GITHUB_OUTPUT": str(output),
                },
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(
                output.read_text().splitlines(),
                ["core=true", "report=true", "mermaid=true", "full=true"],
            )


if __name__ == "__main__":
    unittest.main()
