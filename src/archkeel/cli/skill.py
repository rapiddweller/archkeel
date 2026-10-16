# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Install the Archkeel coding-agent skill into a repository."""

from enum import StrEnum
from importlib.resources import files
from pathlib import Path


class InstallationAgent(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"


class _LegacyMarker(StrEnum):
    START = "<!-- archkeel:start -->"
    END = "<!-- archkeel:end -->"


def _skill_text() -> str:
    return files("archkeel.cli").joinpath("assets", "SKILL.md").read_text(encoding="utf-8")


def install_skill(root: Path, agent: InstallationAgent | str) -> Path:
    """Write or update the Archkeel skill for the given coding agent under root."""
    agent = InstallationAgent(agent)
    agents_path = root / "AGENTS.md"
    updated = None
    if agent is InstallationAgent.CODEX and agents_path.exists():
        existing = agents_path.read_bytes().decode("utf-8")
        start_index = existing.find(_LegacyMarker.START)
        end_index = existing.find(_LegacyMarker.END, start_index)
        if _LegacyMarker.START in existing or _LegacyMarker.END in existing:
            if (
                existing.count(_LegacyMarker.START) != 1
                or existing.count(_LegacyMarker.END) != 1
                or end_index < start_index
            ):
                raise ValueError(f"{agents_path} has malformed Archkeel markers")
            # Validate before writing either file; leave surrounding user text byte-for-byte.
            updated = existing[:start_index] + existing[end_index + len(_LegacyMarker.END) :]

    target = (
        root
        / (".claude" if agent is InstallationAgent.CLAUDE else ".agents")
        / "skills/archkeel/SKILL.md"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_skill_text(), encoding="utf-8")
    if updated is not None:
        agents_path.write_text(updated, encoding="utf-8")
    return target
