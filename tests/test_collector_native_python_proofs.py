# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare the import-local proofs needed by member convergence (AD-404)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from test_collector_native_python_parse import _minor


def _native(binary: Path, root: Path, paths: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(
        [str(binary), "--dump-proofs", str(_minor()), str(root)],
        input="".join(f"{path}\n" for path in paths),
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    )
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_import_local_proof_dump_exists(tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(
        "from builtins import staticmethod as static\n"
        "class C:\n    @static\n    def f(): pass\n"
    )
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert row["full_scope"], row
    assert row["data"]["stable"] == ["C", "static"]
