# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The installed story guidance is usable and does not replace repository files."""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from archkeel.explorer_story_spec import _validate

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_real_skill_install_creates_a_valid_example_and_preserves_edits(
    tmp_path: Path, agent: str
) -> None:
    command = [
        sys.executable,
        "-m",
        "archkeel.cli",
        "skill",
        "install",
        agent,
        "--root",
        str(tmp_path),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    folder = tmp_path / ".archkeel" / "templates"
    template, example = folder / "story.md", folder / "example.story.json"
    assert template.is_file()
    spec = json.loads(example.read_text())
    _validate(spec)
    jsonschema.validate(spec, json.loads((ROOT / "schema/view-spec.schema.json").read_text()))
    assert not (tmp_path / ".archkeel" / "stories").exists()
    template.write_text("User guidance")
    example.write_text("User example")
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode == 0, second.stdout + second.stderr
    assert template.read_text() == "User guidance"
    assert example.read_text() == "User example"


def test_install_refuses_a_linked_template_directory(tmp_path: Path) -> None:
    from archkeel.cli.skill import install_skill

    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (tmp_path / ".archkeel").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(ValueError, match="cannot be a link"):
        install_skill(tmp_path, "codex")
    assert list(outside.iterdir()) == []
