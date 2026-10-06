# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Routing rules for the lightweight CI change classifier."""

from __future__ import annotations

import unittest

from tools.ci_changes import Areas, classify_path, classify_paths


class ChangeClassificationTests(unittest.TestCase):
    def test_path_capabilities(self) -> None:
        cases = (
            ("src/archkeel/check/report.py", Areas(core=True, report=True)),
            ("src/archkeel/render/html.py", Areas(core=True, report=True)),
            (
                "src/archkeel/render/assets/archkeel-logo-dark.svg",
                Areas(core=True, report=True),
            ),
            (
                "src/archkeel/render/assets/archkeel-logo-light.svg",
                Areas(core=True, report=True),
            ),
            ("src/archkeel/render/assets/archkeel-mark.png", Areas(core=True, report=True)),
            ("Makefile", Areas(core=True, report=True, mermaid=True)),
            (".github/workflows/ci.yml", Areas(core=True, report=True, mermaid=True)),
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


if __name__ == "__main__":
    unittest.main()
