# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TypeScript standard-library catalog: the loader of `standard_libs.json` (AD-261).

`tools/typescript_libs.py` generates the data file from the compiler's lib files. The native
collector will embed the same file, so this module holds the code that reads it and no data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, TypedDict

# The data file sits next to this module in the wheel and the sdist. `importlib.resources` would
# import `tempfile` and `zipfile` on every scan for a file that is never inside a zip.
_DATA: Final[Path] = Path(__file__).with_name("standard_libs.json")


class CatalogError(ValueError):
    """The data file is missing or broken, so the install is broken."""


class _Entry(TypedDict):
    globals: list[str]
    references: list[str]


class _Catalog(TypedDict):
    typescript_version: str
    libs: dict[str, _Entry]
    defaults: dict[str, list[str]]


_KNOWN: dict[str, StandardLibrary]


class StandardLibrary(str):
    """A `lib` value the pinned compiler accepts; the data file is the only list of them."""

    __slots__ = ()

    def __new__(cls, name: str) -> StandardLibrary:
        try:
            return _KNOWN[name]
        except KeyError:
            raise ValueError(f"{name!r} is not a valid StandardLibrary") from None

    def __reduce__(self) -> tuple[type[StandardLibrary], tuple[str]]:
        # Protocols 0 and 1 would otherwise rebuild a plain copy, not the registered instance.
        return (StandardLibrary, (str(self),))


def _load(
    path: Path,
) -> tuple[
    str,
    dict[StandardLibrary, frozenset[str]],
    dict[StandardLibrary, tuple[StandardLibrary, ...]],
    dict[str, tuple[StandardLibrary, ...]],
    dict[str, StandardLibrary],
]:
    """Read the data file; the last item holds each name once, as its registered instance."""
    try:
        data: _Catalog = json.loads(path.read_bytes())
        entries: dict[str, _Entry] = data["libs"]
        defaults: dict[str, list[str]] = data["defaults"]
        version = data["typescript_version"]
        if not entries:
            raise ValueError("the file lists no libs")
        known = {name: str.__new__(StandardLibrary, name) for name in entries}

        def named(names: list[str]) -> tuple[StandardLibrary, ...]:
            return tuple(known[name] for name in names)

        return (
            version,
            {known[name]: frozenset(entry["globals"]) for name, entry in entries.items()},
            {known[name]: named(entry["references"]) for name, entry in entries.items()},
            {target: named(names) for target, names in defaults.items()},
            known,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise CatalogError(
            f"{path}: broken install, cannot read the catalog ({error!r})"
        ) from error


TYPESCRIPT_VERSION, LIB_GLOBALS, LIB_REFERENCES, DEFAULT_LIBS, _KNOWN = _load(_DATA)
