# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-derived provenance for language collectors."""

import hashlib
import importlib.metadata
import platform
import re
import tomllib
from pathlib import Path
from typing import Literal

from archkeel.ir.facts import AnalyzerInfo, RuntimeInfo, RuntimeRequirementState

Language = Literal["python", "dart", "typescript"]
_ANALYZERS: dict[Language, str] = {
    "python": "archkeel-python-analyzer",
    "dart": "archkeel-dart-analyzer",
    "typescript": "archkeel-typescript-imports",
}
# A parser change can change facts without changing a line of this package.
_PARSERS = ("tree-sitter", "tree-sitter-typescript")


def collector_provenance(
    language: Language,
    *,
    required: str | None = ">=3.11",
    requirement_state: RuntimeRequirementState = "declared",
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
        RuntimeInfo("python", platform.python_version(), required, requirement_state),
    )


def python_requirement(root: Path) -> tuple[str | None, RuntimeRequirementState]:
    path = root / "pyproject.toml"
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            return None, "metadata_invalid"
        metadata = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "metadata_missing"
    except (OSError, ValueError):
        return None, "metadata_invalid"
    project = metadata.get("project")
    if isinstance(project, dict) and "requires-python" in project:
        required = project["requires-python"]
    else:
        tool = metadata.get("tool")
        poetry = tool.get("poetry") if isinstance(tool, dict) else None
        dependencies = poetry.get("dependencies") if isinstance(poetry, dict) else None
        if not isinstance(dependencies, dict) or "python" not in dependencies:
            return None, "requirement_missing"
        required = dependencies["python"]
        if not isinstance(required, str) or not required.strip():
            return None, "requirement_invalid"
        required = _normalize_poetry_caret(required)
    if not isinstance(required, str) or not required.strip():
        return None, "requirement_invalid"
    return required, "declared"


def _normalize_poetry_caret(required: str) -> str:
    match = re.fullmatch(r"\^([1-9][0-9]*(?:\.[0-9]+){0,2})", required.strip())
    if match is None:
        return required
    version = match.group(1)
    try:
        numbers = [int(part) for part in version.split(".")]
        upper_bound = f"{numbers[0] + 1}.0"
    except ValueError:
        return required
    return f">={version},<{upper_bound}"
