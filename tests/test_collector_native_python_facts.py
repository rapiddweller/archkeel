# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source fact dump boundaries, compared with the unchanged Python functions (AD-412)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from test_collector_native_python_parse import _minor


def native(binary: Path, root: Path, flag: str, request: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        [str(binary), flag, str(_minor()), str(root)],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        timeout=10,
        check=True,
    )
    return json.loads(result.stdout)


def test_lexical_dump_exists(tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text("x = 1\ndef f(a): return a + x\n")
    row = native(python_dump_binary, tmp_path, "--dump-lexical", {"file": "probe.py"})
    assert row["full_scope"], row
    assert row["data"]["names"]
