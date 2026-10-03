# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-derived provenance for language collectors."""

import hashlib
import importlib.metadata
import platform
from pathlib import Path
from typing import Literal

from archkeel.ir.facts import AnalyzerInfo, RuntimeInfo

Language = Literal["python", "dart"]


def collector_provenance(language: Language) -> tuple[AnalyzerInfo, RuntimeInfo]:
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
    try:
        version = importlib.metadata.version("archkeel")
    except importlib.metadata.PackageNotFoundError:
        version = "0+unknown"
    return (
        AnalyzerInfo(
            "archkeel-python-analyzer" if language == "python" else "archkeel-dart-directives",
            version,
            digest.hexdigest(),
        ),
        RuntimeInfo("python", platform.python_version()),
    )
