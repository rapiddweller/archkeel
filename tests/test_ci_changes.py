"""Routing rules for the lightweight CI change classifier."""

from __future__ import annotations

import unittest

from tools.ci_changes import Areas, classify_path, classify_paths


class ChangeClassificationTests(unittest.TestCase):
    def test_path_capabilities(self) -> None:
        cases = (
            ("src/archkeel/check/report.py", Areas(core=True, report=True)),
            ("src/archkeel/render/html.py", Areas(core=True, report=True)),
            ("Makefile", Areas(core=True, report=True, mermaid=True)),
            (".github/workflows/ci.yml", Areas(core=True, report=True, mermaid=True)),
            ("README.md", Areas(mermaid=True)),
            ("docs/architecture/archkeel.md", Areas(mermaid=True)),
            ("skills/archkeel/SKILL.md", Areas(core=True, mermaid=True)),
            ("tools/mermaid_blocks.py", Areas(core=True, mermaid=True)),
            ("tests/test_mermaid.py", Areas(core=True, mermaid=True)),
            ("src/archkeel/check/analyzer.py", Areas(core=True)),
            ("unmapped/product/contract.yaml", Areas(core=True)),
            ("unmapped/notes.md", Areas(core=True, mermaid=True)),
            ("docs/screenshots/report.PNG", Areas()),
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
