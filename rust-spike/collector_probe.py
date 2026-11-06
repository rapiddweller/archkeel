"""Run a synthetic fail-closed probe through ProcessCollector."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def main() -> None:
    if sys.version_info[:2] != (3, 11):
        raise SystemExit(f"run this recorded probe with CPython 3.11, got {sys.version}")
    sys.path.insert(0, str(REPOSITORY / "src"))
    from archkeel.analyzer.process import ProcessCollector
    from archkeel.ir.protocol import (
        CollectionRequest,
        ProtocolVersion,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    root = Path(tempfile.mkdtemp(prefix="rust-child-probe-"))
    source = root / "src" / "sample" / "api.py"
    source.parent.mkdir(parents=True)
    source.write_text("def identity[T](value: T) -> T: ...\nimport hidden\n")
    request = CollectionRequest(
        SnapshotInput(str(root), "0" * 40, False),
        SourceScope(("src",), "sample"),
        PythonSettings(),
        ProtocolVersion.V4,
    )

    extension = Path(__file__).parent / "target" / "debug" / "_core.cpython-311-darwin.so"
    os.environ["ARCHKEEL_RUST_IMPORT_CORE_PATH"] = str(extension)
    os.environ["ARCHKEEL_RUST_PYTHON_TARGET"] = "3.11"
    child = ProcessCollector(
        (sys.executable, "-I", "-B", str(Path(__file__).with_name("collector_child_entry.py")))
    )
    result = child.collect(request)
    if not hasattr(result, "coverage"):
        raise AssertionError(result)
    if not result.coverage.gaps or result.imports:
        raise AssertionError("unsupported syntax did not fail closed")
    print(
        "collector child fail-closed probe passed; "
        f"gaps={len(result.coverage.gaps)}, import targets={len(result.imports)}"
    )


if __name__ == "__main__":
    main()
