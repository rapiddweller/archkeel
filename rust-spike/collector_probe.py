"""Run a synthetic fail-closed probe through ProcessCollector."""

from __future__ import annotations

import ast
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
    source_root = root / "src" / "sample"
    source_root.mkdir(parents=True)
    source = source_root / "new_syntax.py"
    source.write_text("match value:\n    case _:\n        import hidden\n")
    (source_root / "valid.py").write_text("import math\n")
    ast.parse(source.read_text())
    request = CollectionRequest(
        SnapshotInput(str(root), "0" * 40, False),
        SourceScope(("src",), "sample"),
        PythonSettings(),
        ProtocolVersion.V4,
    )

    extension = Path(__file__).parent / "target" / "debug" / "_core.cpython-311-darwin.so"
    os.environ["ARCHKEEL_RUST_IMPORT_CORE_PATH"] = str(extension)
    os.environ["ARCHKEEL_RUST_PYTHON_TARGET"] = "3.9"
    child = ProcessCollector(
        (sys.executable, "-I", "-B", str(Path(__file__).with_name("collector_child_entry.py")))
    )
    result = child.collect(request)
    if not hasattr(result, "coverage"):
        raise AssertionError(result)
    rust_gaps = [gap for gap in result.coverage.gaps if gap.kind == "RustUnsupportedSyntaxError"]
    if len(rust_gaps) != 1 or len(result.imports) != 1:
        raise AssertionError("unsupported syntax did not fail closed")
    print(
        "collector child fail-closed probe passed; "
        f"rust-specific gaps={len(rust_gaps)}, positive-control imports={len(result.imports)}"
    )


if __name__ == "__main__":
    main()
