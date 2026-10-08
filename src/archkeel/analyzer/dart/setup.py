# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Prepare the pinned Analyzer package explicitly, outside collection runs."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    package = Path(__file__).with_name("native")
    executable = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if executable is None:
        print(
            "Dart SDK not found; install Dart before running archkeel-dart-setup", file=sys.stderr
        )
        return 2
    if Path(executable).suffix.lower() in {".bat", ".cmd"}:
        print("Dart SDK must expose a native executable, not a .bat/.cmd shim", file=sys.stderr)
        return 2
    try:
        return subprocess.run(
            [executable, "pub", "get", "--enforce-lockfile"], cwd=package, check=False
        ).returncode
    except OSError as error:
        print(f"Could not prepare Dart collector dependencies: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
