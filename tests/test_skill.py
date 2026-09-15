# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Tests for installing the Archkeel coding-agent skill."""

from pathlib import Path

import pytest

from archkeel.cli.skill import install_skill

ROOT = Path(__file__).parents[1]
ASSET = ROOT / "src" / "archkeel" / "cli" / "assets" / "SKILL.md"


def test_claude_writes_the_asset_unchanged(tmp_path: Path) -> None:
    target = install_skill(tmp_path, "claude")
    assert target == tmp_path / ".claude" / "skills" / "archkeel" / "SKILL.md"
    assert target.read_bytes() == ASSET.read_bytes()


def test_claude_install_is_idempotent(tmp_path: Path) -> None:
    first = install_skill(tmp_path, "claude")
    before = first.read_bytes()
    second = install_skill(tmp_path, "claude")
    assert second.read_bytes() == before


def test_codex_strips_frontmatter(tmp_path: Path) -> None:
    path = install_skill(tmp_path, "codex")
    body = path.read_text(encoding="utf-8")
    assert "name: archkeel" not in body
    assert "description:" not in body
    assert "# Archkeel" in body


def test_codex_creates_agents_md_when_missing(tmp_path: Path) -> None:
    path = install_skill(tmp_path, "codex")
    assert path == tmp_path / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("<!-- archkeel:start -->\n")
    assert text.rstrip("\n").endswith("<!-- archkeel:end -->")


def test_codex_preserves_surrounding_user_text(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("Existing content untouched.\n\nMore notes.\n", encoding="utf-8")
    install_skill(tmp_path, "codex")
    text = agents.read_text(encoding="utf-8")
    assert text.startswith("Existing content untouched.\n\nMore notes.\n\n<!-- archkeel:start -->")


def test_codex_replaces_an_existing_section_in_place(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "Before.\n\n<!-- archkeel:start -->\nstale body\n<!-- archkeel:end -->\n\nAfter.\n",
        encoding="utf-8",
    )
    install_skill(tmp_path, "codex")
    text = agents.read_text(encoding="utf-8")
    assert text.startswith("Before.\n\n<!-- archkeel:start -->\n")
    assert text.endswith("<!-- archkeel:end -->\n\nAfter.\n")
    assert "stale body" not in text
    assert "# Archkeel" in text


def test_codex_install_is_idempotent(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("Notes.\n", encoding="utf-8")
    install_skill(tmp_path, "codex")
    first = agents.read_bytes()
    install_skill(tmp_path, "codex")
    assert agents.read_bytes() == first


def test_codex_raises_on_unmatched_start_marker(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("<!-- archkeel:start -->\nbroken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="archkeel:start"):
        install_skill(tmp_path, "codex")


def test_skill_covers_interview_and_auto_mode() -> None:
    """AD-16: the skill must name both onboarding modes, not just the interview."""
    body = ASSET.read_text(encoding="utf-8")
    assert "Interview mode" in body
    assert "Auto mode" in body
    assert 'decided_by: "architect"' in body
    assert 'decided_by: "agent"' in body


def test_skill_asks_why_on_a_deviation_from_its_recommendation() -> None:
    """AD-16: interview mode asks why before writing a rule against its own recommendation."""
    body = ASSET.read_text(encoding="utf-8")
    assert "ask why before writing the rule" in body
