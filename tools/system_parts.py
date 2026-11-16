# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The parts of ArchKeel as one system, read from one document (AD-522).

`docs/architecture/architecture-system.json` has the shape of the first slice of the system
contract: a title and parts, each with an id, a title and the scan configuration it names. The
language and the roots of a part come from its configuration, so no field of the document names a
language. The core runs this document in one system run (AD-612, `make self-validate-system`).
The gallery and its system page still take the title and the parts from here, and join the
verdicts in `tools/report_product.py`, until the report draws a system frame (AD-522).
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs" / "architecture" / "architecture-system.json"
MAX_PARTS = 64
ID = re.compile(r"[a-z][a-z0-9-]{0,30}")


@dataclass(frozen=True)
class SystemPart:
    id: str  # the stable file name in the gallery: self/<id>.html
    title: str  # the name of the part
    config: str  # the scan configuration of the part, relative to the repository root
    language: str  # from the configuration: scan.language, upper case
    subject: str  # the title and the scan roots of the configuration

    @property
    def label(self) -> str:
        return f"{self.id} self-check"


@dataclass(frozen=True)
class System:
    title: str
    parts: tuple[SystemPart, ...]

    @property
    def name(self) -> str:
        """The title and the parts, for a heading: `ArchKeel (Python shell + Rust core)`."""
        return f"{self.title} ({' + '.join(part.title for part in self.parts)})"


def _text(item: object, key: str) -> str:
    value = item.get(key) if isinstance(item, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"the system document needs a text for `{key}`")
    return value


def _scan(config: str, root: Path) -> tuple[str, list[str]]:
    try:
        table = tomllib.loads((root / config).read_text()).get("scan", {})
    except (OSError, ValueError):
        return "", []
    roots = table.get("roots", [])
    return str(table.get("language", "python")), [r for r in roots if isinstance(r, str)]


def load(document: Path = DOCUMENT, root: Path = ROOT) -> System:
    """The system of a document. A document with no part, a repeated id or a bad key is refused."""
    data = json.loads(document.read_text())
    if not isinstance(data, dict) or data.get("kind") != "system":
        raise ValueError("the system document needs `kind: system`")
    raw = data.get("parts")
    if not isinstance(raw, list) or not 0 < len(raw) <= MAX_PARTS:
        raise ValueError(f"the system document needs 1 to {MAX_PARTS} parts")
    parts: list[SystemPart] = []
    for item in raw:
        identifier = _text(item, "id")
        if not ID.fullmatch(identifier) or any(part.id == identifier for part in parts):
            raise ValueError(f"the part id `{identifier}` is not valid or is repeated")
        config, title = _text(item, "config"), _text(item, "title")
        language, roots = _scan(config, root)
        subject = f"{title} ({', '.join(roots)})" if roots else title
        parts.append(SystemPart(identifier, title, config, language.upper(), subject))
    return System(_text(data, "title"), tuple(parts))
