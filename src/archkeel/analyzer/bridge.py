# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Subprocess bridge for the bundled Python analyzer."""

import json
import platform
import sys
from pathlib import Path

from .embedded.report import analyze_snapshot


def main() -> None:
    request = json.load(sys.stdin)
    model, code = analyze_snapshot(
        Path(request["source_root"]),
        git_head=request["git_head"],
        dirty=request["dirty"],
        contract_root=Path(request["contract_root"]),
        contract_path=Path(request["contract"]),
        roots=tuple(request["roots"]),
        namespace=request["namespace"],
        language=request["language"],
    )
    model["python_version"] = platform.python_version()
    json.dump({"model": model, "exit_code": code}, sys.stdout, sort_keys=True)


if __name__ == "__main__":
    main()
