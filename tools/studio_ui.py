# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compile Studio TypeScript or verify the JavaScript shipped with the package."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src/archkeel/cli/assets"
COMPILER = ROOT / "tools/browser-runtime/node_modules/typescript/bin/tsc"


def compile_into(output: Path) -> None:
    """Use the pinned compiler and the Studio project settings."""
    subprocess.run(
        ["node", str(COMPILER), "--project", str(ROOT / "studio"), "--outDir", str(output)],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not COMPILER.is_file():
        raise SystemExit("Install the pinned compiler with make browser-runtime-install.")
    if not args.check:
        compile_into(ASSETS)
        return

    with TemporaryDirectory() as directory:
        output = Path(directory)
        compile_into(output)
        generated = {file.relative_to(output) for file in output.rglob("*.js")}
        shipped = {
            file.relative_to(ASSETS)
            for prefix in ("explorer", "studio")
            for file in ASSETS.glob(f"{prefix}*.js")
        }
        stale = generated ^ shipped
        stale.update(
            file
            for file in generated & shipped
            if (output / file).read_bytes() != (ASSETS / file).read_bytes()
        )
        if stale:
            names = ", ".join(str(file) for file in sorted(stale))
            raise SystemExit(
                f"Studio JavaScript is missing, stale or extra: {names}. "
                "Run make studio-ui-generate and review the files."
            )


if __name__ == "__main__":
    main()
