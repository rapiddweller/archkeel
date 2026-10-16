# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Publish the one authored Flow program without optimization or name changes."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_ASSETS = _ROOT / "src/archkeel/render/assets"
_SOURCE = _ASSETS / "flow.js"
_OUTPUT = _ASSETS / "flow.runtime.js"
_TOOLS = _ROOT / "tools/browser-runtime"
_COMPILER = _TOOLS / "node_modules/terser/bin/terser"
_OPTIONS = _TOOLS / "options.json"


def runtime_bytes() -> bytes:
    node = shutil.which("node")
    if node is None:
        raise SystemExit("Flow publication requires Node; installed reports do not.")
    source = _SOURCE.read_bytes()
    result = subprocess.run(
        [node, str(_COMPILER), "--config-file", str(_OPTIONS)],
        input=source,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    provenance = (
        f"// Generated from flow.js; source-sha256={sha256(source).hexdigest()}\n"
        "// Owner: tools/browser_runtime.py. Edit flow.js; make browser-runtime-generate.\n"
    )
    return provenance.encode("utf-8") + result.stdout


def check() -> None:
    if _OUTPUT.read_bytes() != runtime_bytes():
        raise SystemExit("Flow runtime is stale; run make browser-runtime-generate.")


def generate() -> None:
    _OUTPUT.write_bytes(runtime_bytes())


class _Arguments(argparse.Namespace):
    check: bool = False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(namespace=_Arguments())
    if arguments.check:
        check()
    else:
        generate()


if __name__ == "__main__":
    main()
