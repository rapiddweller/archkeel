# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replace this process with the prepared native Dart collector."""

import os
import shutil
from pathlib import Path


def main() -> int:
    package = Path(__file__).with_name("native")
    packages = package / ".dart_tool" / "package_config.json"
    script = package / "bin" / "collect.dart"
    if not packages.is_file() or not script.is_file():
        raise SystemExit("Dart collector is not prepared; run archkeel-dart-setup")
    executable = os.environ.get("DART_EXECUTABLE") or shutil.which("dart")
    if executable is None:
        raise SystemExit("Dart SDK not found; install Dart and run archkeel-dart-setup")
    if Path(executable).suffix.lower() in {".bat", ".cmd"}:
        raise SystemExit("Dart SDK must expose a native executable, not a .bat/.cmd shim")
    argv = [executable, f"--packages={packages.resolve()}", str(script.resolve())]
    os.execvpe(executable, argv, os.environ)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
