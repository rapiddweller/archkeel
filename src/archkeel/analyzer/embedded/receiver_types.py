# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Statically known receiver types and the method calls they resolve.

`dir()` would answer which methods a type carries, but the answer moves with the interpreter
that happens to run the analyzer, which AD-7 forbids for a deterministic result. Each table
below is copied by hand from the type's documented public methods instead, so the same source
resolves to the same targets on every supported interpreter, never on whichever one is running.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Literal

# Each entry names the qualified type the target is reported under, and the methods it
# resolves. `str` and `Path` share the same shape as `list`/`dict`/`set`; nothing here reads
# an instance to decide, only the type name the caller already established. The library
# types below are keyed by their qualified name, so an annotation spelled `Table` never
# reaches them: only a constructor or a return the import binding proves does (AD-40).
_METHOD_TABLES: dict[str, tuple[str, frozenset[str]]] = {
    "list": (
        "builtins.list",
        frozenset(("append clear copy count extend index insert pop remove reverse sort").split()),
    ),
    "dict": (
        "builtins.dict",
        frozenset(
            ("clear copy fromkeys get items keys pop popitem setdefault update values").split()
        ),
    ),
    "set": (
        "builtins.set",
        frozenset(
            (
                "add clear copy difference difference_update discard intersection "
                "intersection_update isdisjoint issubset issuperset pop remove "
                "symmetric_difference symmetric_difference_update union update"
            ).split()
        ),
    ),
    "frozenset": (
        "builtins.frozenset",
        frozenset(
            (
                "copy difference intersection isdisjoint issubset issuperset symmetric_difference "
                "union"
            ).split()
        ),
    ),
    "tuple": ("builtins.tuple", frozenset("count index".split())),
    "str": (
        "builtins.str",
        frozenset(
            (
                "capitalize casefold center count encode endswith expandtabs find format "
                "format_map index isalnum isalpha isascii isdecimal isdigit isidentifier islower "
                "isnumeric isprintable isspace istitle isupper join ljust lower lstrip maketrans "
                "partition removeprefix removesuffix replace rfind rindex rjust rpartition rsplit "
                "rstrip split splitlines startswith strip swapcase title translate upper zfill"
            ).split()
        ),
    ),
    "Path": (
        "pathlib.Path",
        frozenset(
            (
                "absolute as_posix as_uri chmod exists expanduser glob is_absolute is_dir is_file "
                "is_symlink iterdir joinpath lstat mkdir read_bytes read_text relative_to rename "
                "replace resolve rglob rmdir samefile stat touch unlink with_name with_stem "
                "with_suffix write_bytes write_text"
            ).split()
        ),
    ),
    "hashlib._Hash": ("hashlib._Hash", frozenset("copy digest hexdigest update".split())),
    "argparse.ArgumentParser": (
        "argparse.ArgumentParser",
        frozenset(
            (
                "add_argument add_argument_group add_mutually_exclusive_group add_subparsers "
                "error exit format_help format_usage get_default parse_args parse_intermixed_args "
                "parse_known_args parse_known_intermixed_args print_help print_usage register "
                "set_defaults"
            ).split()
        ),
    ),
    "argparse._ArgumentGroup": (
        "argparse._ArgumentGroup",
        frozenset(
            ("add_argument add_argument_group add_mutually_exclusive_group set_defaults").split()
        ),
    ),
    "argparse._SubParsersAction": ("argparse._SubParsersAction", frozenset("add_parser".split())),
    "rich.console.Console": (
        "rich.console.Console",
        frozenset(
            (
                "begin_capture bell capture clear control end_capture export_html export_svg "
                "export_text get_style input line log measure out pager pop_render_hook pop_theme "
                "print print_exception print_json push_render_hook push_theme render render_lines "
                "render_str rule save_html save_svg save_text screen set_alt_screen "
                "set_window_title show_cursor status update_screen update_screen_lines use_theme"
            ).split()
        ),
    ),
    "rich.table.Table": (
        "rich.table.Table",
        frozenset(("add_column add_row add_section get_row_style grid").split()),
    ),
}

# A callable reached through an import binding whose documented result is a table type.
# `hashlib.new` takes the algorithm by name and still returns the one hash object type.
_CONSTRUCTORS: dict[str, str] = {
    "pathlib.Path": "Path",
    "argparse.ArgumentParser": "argparse.ArgumentParser",
    "rich.console.Console": "rich.console.Console",
    "rich.table.Table": "rich.table.Table",
    **{
        f"hashlib.{name}": "hashlib._Hash"
        for name in (
            "new",
            "md5",
            "sha1",
            "sha224",
            "sha256",
            "sha384",
            "sha512",
            "sha3_224",
            "sha3_256",
            "sha3_384",
            "sha3_512",
            "blake2b",
            "blake2s",
        )
    },
}

# A method on a table type whose documented return is itself a table type, so a chain such
# as `parser.add_subparsers(...).add_parser(...)` stays typed one step at a time (AD-40).
_METHOD_RETURNS: dict[tuple[str, str], str] = {
    ("argparse.ArgumentParser", "add_subparsers"): "argparse._SubParsersAction",
    ("argparse.ArgumentParser", "add_argument_group"): "argparse._ArgumentGroup",
    ("argparse.ArgumentParser", "add_mutually_exclusive_group"): "argparse._ArgumentGroup",
    ("argparse._ArgumentGroup", "add_argument_group"): "argparse._ArgumentGroup",
    ("argparse._ArgumentGroup", "add_mutually_exclusive_group"): "argparse._ArgumentGroup",
    ("argparse._SubParsersAction", "add_parser"): "argparse.ArgumentParser",
    ("hashlib._Hash", "copy"): "hashlib._Hash",
    **{
        ("Path", name): "Path"
        for name in (
            "resolve",
            "absolute",
            "expanduser",
            "joinpath",
            "relative_to",
            "with_name",
            "with_stem",
            "with_suffix",
            "rename",
            "replace",
        )
    },
}

# An annotation may spell the same type two ways (`Path` imported by name, or `pathlib.Path`
# written out); both name the one type_name the method table is keyed by.
_ANNOTATION_BASES = {
    "list": "list",
    "dict": "dict",
    "set": "set",
    "frozenset": "frozenset",
    "tuple": "tuple",
    "str": "str",
    "Path": "Path",
    "pathlib.Path": "Path",
}

# A literal or a zero-argument-shaped constructor call proves its result's type outright;
# `set()` has no literal spelling, so only the call form is recognised for it.
_LITERAL_CONSTRUCTORS = {"list": "list", "dict": "dict", "set": "set"}


Origin = Literal["literal", "annotation", "documented"]


@dataclass(frozen=True, slots=True)
class ReceiverType:
    """A receiver's statically known type, and how sure the analyzer is of it.

    `origin` is "literal" when the value was built in front of the analyzer (a literal or a
    builtin constructor call), "annotation" when it is read off a declared type instead,
    which Python never checks at runtime, and "documented" when it is the return of a
    library call the import binding names (AD-40). `resolve_name` turns the first into
    `resolved` and the other two into `partially_resolved` (AD-37).
    """

    type_name: str
    origin: Origin


def constructor_receiver_type(qualified_callee: str) -> str | None:
    """Name the type a call to this import-bound callable returns, or None (AD-40)."""
    return _CONSTRUCTORS.get(qualified_callee)


def method_return_type(type_name: str, method: str) -> str | None:
    """Name the type `type_name.method(...)` returns, or None outside the table (AD-40)."""
    return _METHOD_RETURNS.get((type_name, method))


def literal_receiver_type(node: ast.expr) -> str | None:
    """Read the type a literal expression or a builtin constructor call carries."""
    if isinstance(node, ast.List | ast.ListComp):
        return "list"
    if isinstance(node, ast.Dict | ast.DictComp):
        return "dict"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "str"
    if isinstance(node, ast.JoinedStr):
        return "str"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return _LITERAL_CONSTRUCTORS.get(node.func.id)
    return None


def annotation_receiver_type(annotation: str | None) -> str | None:
    """Read the bare type name off an annotation; a generic subscript keeps only its base."""
    if not annotation:
        return None
    base = annotation.split("[", 1)[0].strip()
    return _ANNOTATION_BASES.get(base)


def receiver_call_target(type_name: str, method: str) -> str | None:
    """Name the qualified target `type_name.method` resolves to, or None outside the table."""
    table = _METHOD_TABLES.get(type_name)
    if table is None:
        return None
    prefix, methods = table
    return f"{prefix}.{method}" if method in methods else None
