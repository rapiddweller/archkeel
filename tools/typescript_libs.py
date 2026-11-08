# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Generate the TypeScript standard-library catalog from the pinned compiler's lib files.

The compiler's lib table names the values a `lib` option accepts, and each name is one
`lib.*.d.ts` file. A file's top-level value declarations are the globals it proves, and its
`/// <reference lib>` lines are its dependencies. The result is one JSON file that the Python
collector loads and the native collector embeds. `--check` fails when the checked-in file differs
from what the pinned compiler produces; `--write` (the default) regenerates it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
TYPESCRIPT: Final = ROOT / "tools/browser-runtime/node_modules/typescript"
OUTPUT: Final = ROOT / "src/archkeel/analyzer/typescript/standard_libs.json"

_LIB_TABLE: Final = re.compile(r"var libEntries = \[(.*?)\];", re.DOTALL)
_TARGET_TABLE: Final = re.compile(r"var targetToLibMap = .*?new Map\(\[(.*?)\]\);", re.DOTALL)
_LIB_ENTRY: Final = re.compile(r'\["([a-z0-9.]+)", "(lib\.[a-z0-9.]+\.d\.ts)"\]')
_TARGET_ENTRY: Final = re.compile(r'\[\d+ /\* (\w+) \*/, "(lib\.[a-z0-9.]+\.d\.ts)"\]')
_GLOBAL: Final = re.compile(
    r"^declare (?:abstract )?(?:var|function|class|namespace|const|let) ([A-Za-z0-9_$]+)",
    re.MULTILINE,
)
_REFERENCE: Final = re.compile(r'^/// <reference lib="([a-z0-9.]+)" />', re.MULTILINE)
# The compiler gives ES6 the same value as ES2015, so both targets share one default file.
_TARGET_ALIAS: Final = {"es6": "es2015"}
# getDefaultLibFileName's default branch: ES3 and ES5 (and no target at all).
_ES5_TARGETS: Final = ("es3", "es5")
_ES5_DEFAULT_FILE: Final = "lib.d.ts"


def _table(pattern: re.Pattern[str], text: str, what: str) -> str:
    found = pattern.search(text)
    if found is None:
        raise SystemExit(f"typescript_libs: could not find the compiler's {what} table")
    return found.group(1)


def _read(file_name: str) -> tuple[list[str], list[str]]:
    text = (TYPESCRIPT / "lib" / file_name).read_text(encoding="utf-8")
    return sorted(set(_GLOBAL.findall(text))), _REFERENCE.findall(text)


def build_catalog() -> str:
    text = (TYPESCRIPT / "lib" / "typescript.js").read_text(encoding="utf-8")
    version = json.loads((TYPESCRIPT / "package.json").read_text(encoding="utf-8"))["version"]
    # A Map keeps the last entry for a repeated name, as the compiler does.
    files: dict[str, str] = dict(_LIB_ENTRY.findall(_table(_LIB_TABLE, text, "lib")))
    default_files: dict[str, str] = {
        name.lower(): file
        for name, file in _TARGET_ENTRY.findall(_table(_TARGET_TABLE, text, "default lib"))
    }
    for name, file in files.items():
        if not (TYPESCRIPT / "lib" / file).is_file():
            raise SystemExit(f"typescript_libs: {name} names a missing file {file}")
    libs = {name: _read(file) for name, file in sorted(files.items())}
    for name, (_, references) in libs.items():
        unknown = sorted(set(references) - set(files))
        if unknown:
            raise SystemExit(f"typescript_libs: {name} references unknown libs {unknown}")

    # The targets are the compiler's own, plus the ones its table leaves out: ES3 and ES5 share
    # the default file, and ES6 shares ES2015's. A test checks them against ScriptTarget.
    defaults: dict[str, list[str]] = {}
    for target in sorted({*default_files, *_TARGET_ALIAS, *_ES5_TARGETS}):
        if target in _ES5_TARGETS:
            file = _ES5_DEFAULT_FILE
        else:
            file = default_files[_TARGET_ALIAS.get(target, target)]
        defaults[target] = _read(file)[1]

    catalog = {
        "typescript_version": version,
        "libs": {
            name: {"globals": names, "references": references}
            for name, (names, references) in libs.items()
        },
        "defaults": defaults,
    }
    return json.dumps(catalog, separators=(",", ":")) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail when the data file is stale")
    mode.add_argument("--write", action="store_true", help="regenerate the data file (default)")
    args = parser.parse_args(argv)
    # Bytes, not text: the native collector embeds this file, so it is LF on every platform.
    catalog = build_catalog().encode("utf-8")
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != catalog:
            print(f"{OUTPUT.relative_to(ROOT)} is stale; run python -m tools.typescript_libs")
            return 1
        return 0
    OUTPUT.write_bytes(catalog)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
