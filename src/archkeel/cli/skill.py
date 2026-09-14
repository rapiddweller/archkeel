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


def _body(skill_text: str) -> str:
    lines = skill_text.split("\n")
    if lines[0] != "---":
        return skill_text
    end = lines.index("---", 1)
    return "\n".join(lines[end + 1 :]).lstrip("\n")


def install_skill(root: Path, agent: Literal["claude", "codex"]) -> Path:
    """Write or update the Archkeel skill for the given coding agent under root."""
    skill_text = _skill_text()
    if agent == "claude":
        target = root / ".claude" / "skills" / "archkeel" / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(skill_text, encoding="utf-8")
        return target

    agents_path = root / "AGENTS.md"
    body = _body(skill_text).rstrip("\n")
    section = f"{_START}\n{body}\n{_END}\n"
    existing = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    start_index = existing.find(_START)
    if start_index == -1:
        prefix = existing.rstrip("\n")
        updated = f"{prefix}\n\n{section}" if prefix else section
    else:
        end_index = existing.find(_END, start_index)
        if end_index == -1:
            raise ValueError(f"{agents_path} has an archkeel:start marker without an end marker")
        before = existing[:start_index]
        after = existing[end_index + len(_END) :].lstrip("\n")
        updated = f"{before}{section}\n{after}" if after else f"{before}{section}"
    agents_path.write_text(updated, encoding="utf-8")
    return agents_path
