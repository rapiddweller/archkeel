# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-derived provenance for language collectors."""

import hashlib
import importlib.metadata
import platform
import tomllib
from pathlib import Path
from typing import Literal

from archkeel.ir.facts import AnalyzerInfo, RuntimeInfo

Language = Literal["python", "dart", "typescript"]
_ANALYZERS: dict[Language, str] = {
    "python": "archkeel-python-analyzer",
    "dart": "archkeel-dart-directives",
    "typescript": "archkeel-typescript-imports",
}
# A parser change can change facts without changing a line of this package.
_PARSERS = ("tree-sitter", "tree-sitter-typescript")


def collector_provenance(
    language: Language, *, required: str | None = ">=3.11"
) -> tuple[AnalyzerInfo, RuntimeInfo]:
    """Identify the collector from its installed version and its actual source files."""
    package = Path(__file__).parent
    repository = package.parent
    shared = repository / "ir"
    sources = [
        package / "runtime.py",
        *sorted((package / language).rglob("*.py")),
        *(
            shared / name
            for name in (
                "facts.py",
                "identity.py",
                "facts_codec.py",
                "facts_validation.py",
                "protocol.py",
                "state_codec.py",
                "state_facts.py",
                "type_shapes.py",
                "reexports.py",
                "source_records.py",
            )
        ),
    ]
    digest = hashlib.sha256()
    for path in sources:
        digest.update(path.relative_to(repository).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    if language == "typescript":
        for parser in _PARSERS:
            digest.update(f"{parser}=={importlib.metadata.version(parser)}".encode())
            digest.update(b"\0")
    try:
        version = importlib.metadata.version("archkeel")
    except importlib.metadata.PackageNotFoundError:
        version = "0+unknown"
    return (
        AnalyzerInfo(_ANALYZERS[language], version, digest.hexdigest()),
        RuntimeInfo("python", platform.python_version(), required),
    )


def python_requirement(root: Path) -> str | None:
    path = root / "pyproject.toml"
    try:
        if not path.resolve().is_relative_to(root):
            return None
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project")
        required = project.get("requires-python") if isinstance(project, dict) else None
        return required if isinstance(required, str) and required.strip() else None
    except (OSError, ValueError):
        return None
