# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small checked JSON readers shared by the frame and its evidence metadata."""


class CoreError(Exception):
    """The core failed or its frame was refused. The command has no verdict (exit 2)."""


def _object(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CoreError(f"the core frame field {where} is not an object")
    return {str(key): item for key, item in value.items()}


def _text(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise CoreError(f"the core frame field {where} is not a text")
    return value


def _texts(value: object, where: str) -> dict[str, str]:
    return {key: _text(item, f"{where}.{key}") for key, item in _object(value, where).items()}


def _count(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CoreError(f"the core frame field {where} is not a count")
    return value


def _fields(value: object, where: str, names: frozenset[str]) -> dict[str, object]:
    """An object with exactly these fields."""
    found = _object(value, where)
    if missing := sorted(names - found.keys()):
        raise CoreError(f"the core frame field {where} has no field {', '.join(missing)}")
    if extra := sorted(found.keys() - names):
        raise CoreError(f"the core frame field {where} has an unknown field {', '.join(extra)}")
    return found
