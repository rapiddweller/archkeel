# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Tests for installing the Archkeel coding-agent skill."""

import json
import subprocess
import sys
import zipfile
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


def test_codex_writes_native_skill_unchanged(tmp_path: Path) -> None:
    path = install_skill(tmp_path, "codex")
    assert path == tmp_path / ".agents" / "skills" / "archkeel" / "SKILL.md"
    assert path.read_bytes() == ASSET.read_bytes()
    assert not (tmp_path / "AGENTS.md").exists()


def test_codex_preserves_surrounding_user_text(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("Existing content untouched.\n\nMore notes.\n", encoding="utf-8")
    install_skill(tmp_path, "codex")
    text = agents.read_text(encoding="utf-8")
    assert text == "Existing content untouched.\n\nMore notes.\n"


def test_codex_migrates_only_the_managed_section(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "Before.\n\n<!-- archkeel:start -->\nstale body\n<!-- archkeel:end -->\n\nAfter.\n",
        encoding="utf-8",
    )
    install_skill(tmp_path, "codex")
    text = agents.read_text(encoding="utf-8")
    assert text == "Before.\n\n\n\nAfter.\n"
    assert (tmp_path / ".agents/skills/archkeel/SKILL.md").read_bytes() == ASSET.read_bytes()


def test_codex_preserves_crlf_outside_legacy_block(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_bytes(b"Before\r\n<!-- archkeel:start -->old<!-- archkeel:end -->\r\nAfter\r\n")
    install_skill(tmp_path, "codex")
    assert agents.read_bytes() == b"Before\r\n\r\nAfter\r\n"


def test_codex_install_is_idempotent(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("Notes.\n", encoding="utf-8")
    install_skill(tmp_path, "codex")
    first = agents.read_bytes()
    install_skill(tmp_path, "codex")
    assert agents.read_bytes() == first


def test_codex_install_preserves_physical_review_threshold_guidance(tmp_path: Path) -> None:
    body = ASSET.read_text(encoding="utf-8")
    path = install_skill(tmp_path, "codex")
    installed = path.read_text(encoding="utf-8")

    assert "More than seven direct children triggers a review" in body
    assert "Five to seven understandable groups is a review heuristic" in body
    assert "do not hide the excess in `misc`, `utils`, single-child wrappers" in body
    assert installed == body


@pytest.mark.parametrize(
    "markers",
    [
        "<!-- archkeel:start -->\nbroken\n",
        "<!-- archkeel:end -->\n",
        "<!-- archkeel:end --><!-- archkeel:start -->",
        "<!-- archkeel:start --><!-- archkeel:start --><!-- archkeel:end -->",
    ],
)
def test_codex_rejects_malformed_markers_before_writing(tmp_path: Path, markers: str) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text(markers, encoding="utf-8")
    with pytest.raises(ValueError, match="marker"):
        install_skill(tmp_path, "codex")
    assert agents.read_text(encoding="utf-8") == markers
    assert not (tmp_path / ".agents").exists()


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


def test_plugin_package_uses_the_canonical_skill_and_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "plugin"
    command = [sys.executable, "-m", "tools.package_plugin", str(target)]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert (target / "skills/archkeel/SKILL.md").read_bytes() == ASSET.read_bytes()
    portable = json.loads((target / "plugin.json").read_text())
    claude = json.loads((target / ".claude-plugin/plugin.json").read_text())
    assert portable["name"] == claude["name"] == "archkeel"
    assert portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert "mcpServers" not in portable and "hooks" not in portable
    assert (ROOT / "skills/archkeel/SKILL.md").read_bytes() == ASSET.read_bytes()
    marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert marketplace["plugins"] == [{"name": "archkeel", "source": "./"}]
    codex_marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert codex_marketplace["plugins"][0]["source"] == {"source": "local", "path": "./"}
    with zipfile.ZipFile(Path(str(target) + ".zip")) as bundle:
        assert bundle.read("skills/archkeel/SKILL.md") == ASSET.read_bytes()
        assert "assets/archkeel-mark.svg" in bundle.namelist()
    sentinel = target / "user-notes.txt"
    sentinel.write_text("Keep me")
    rerun = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert rerun.returncode != 0
    assert sentinel.read_text() == "Keep me"


def test_plugin_export_preserves_an_existing_zip(tmp_path: Path) -> None:
    target = tmp_path / "plugin.v1"
    archive = Path(str(target) + ".zip")
    archive.write_bytes(b"User file")
    run = subprocess.run(
        [sys.executable, "-m", "tools.package_plugin", str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0
    assert archive.read_bytes() == b"User file"
    assert not target.exists()
