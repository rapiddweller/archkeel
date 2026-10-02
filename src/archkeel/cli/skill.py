# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Install the Archkeel coding-agent skill into a repository."""

from importlib.resources import files
from pathlib import Path
from typing import Literal

_START = "<!-- archkeel:start -->"
_END = "<!-- archkeel:end -->"


def _skill_text() -> str:
    return files("archkeel.cli").joinpath("assets", "SKILL.md").read_text(encoding="utf-8")


def install_skill(root: Path, agent: Literal["claude", "codex"]) -> Path:
    """Write or update the Archkeel skill for the given coding agent under root."""
    agents_path = root / "AGENTS.md"
    updated = None
    if agent == "codex" and agents_path.exists():
        existing = agents_path.read_bytes().decode("utf-8")
        start_index = existing.find(_START)
        end_index = existing.find(_END, start_index)
        if _START in existing or _END in existing:
            if existing.count(_START) != 1 or existing.count(_END) != 1 or end_index < start_index:
                raise ValueError(f"{agents_path} has malformed Archkeel markers")
            # Validate before writing either file; leave surrounding user text byte-for-byte.
            updated = existing[:start_index] + existing[end_index + len(_END) :]

    target = root / (".claude" if agent == "claude" else ".agents") / "skills/archkeel/SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_skill_text(), encoding="utf-8")
    if updated is not None:
        agents_path.write_text(updated, encoding="utf-8")
    return target
