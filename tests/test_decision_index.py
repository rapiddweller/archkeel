# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-752: the index of the decision records is generated from the record files."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import decision_index as index  # noqa: E402

FOLDER = ROOT / "docs/architecture/decisions"


def _folder(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_a_row_has_the_number_the_heading_title_and_the_link_newest_first(tmp_path: Path) -> None:
    folder = _folder(
        tmp_path,
        {
            "ad-02-old.md": "# AD-2: The old one.\n",
            "ad-10-new.md": "# AD-10 The new one\n",
            "ad-24a-letter.md": "# AD-24a A letter\n",
            "ad-3-bare.md": "# A bare heading\n",
        },
    )
    assert index.table(index.records(folder)) == (
        "| Decision | Title |\n|---|---|\n"
        + "| AD-24a | [A letter](ad-24a-letter.md) |\n"
        + "| AD-10 | [The new one](ad-10-new.md) |\n"
        + "| AD-3 | [A bare heading](ad-3-bare.md) |\n"
        + "| AD-2 | [The old one](ad-02-old.md) |\n"
    )


def test_two_records_with_one_number_a_bad_name_and_a_missing_heading_are_faults(
    tmp_path: Path,
) -> None:
    folder = _folder(
        tmp_path,
        {
            "ad-5-first.md": "# AD-5 First\n",
            "ad-05-second.md": "# AD-5 Second\n",
            "ad-x-name.md": "# AD-9 Name\n",
            "ad-7-none.md": "no heading\n",
        },
    )
    faults = "\n".join(index.problems(folder))
    assert "AD-5 is used by 2 records" in faults
    assert "ad-x-name.md: the name is not" in faults
    assert "ad-7-none.md: no first-level heading" in faults


def test_the_tool_writes_the_listing_on_demand(tmp_path: Path) -> None:
    run = [sys.executable, str(ROOT / "tools/decision_index.py")]
    target = tmp_path / "index.md"
    assert subprocess.run([*run, "--write", str(target)], check=True).returncode == 0
    assert target.read_text(encoding="utf-8").startswith("| Decision | Title |\n|---|---|\n| AD-")
