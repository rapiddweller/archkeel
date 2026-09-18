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

_LIST_METHODS = frozenset(
    {
        "append",
        "extend",
        "insert",
        "remove",
        "pop",
        "clear",
        "index",
        "count",
        "sort",
        "reverse",
        "copy",
    }
)

_DICT_METHODS = frozenset(
    {
        "get",
        "keys",
        "values",
        "items",
        "update",
        "pop",
        "popitem",
        "setdefault",
        "clear",
        "copy",
        "fromkeys",
    }
)

_SET_METHODS = frozenset(
    {
        "add",
        "remove",
        "discard",
        "pop",
        "clear",
        "copy",
        "union",
        "intersection",
        "difference",
        "symmetric_difference",
        "update",
        "intersection_update",
        "difference_update",
        "symmetric_difference_update",
        "issubset",
        "issuperset",
        "isdisjoint",
    }
)

_FROZENSET_METHODS = frozenset(
    {
        "copy",
        "union",
        "intersection",
        "difference",
        "symmetric_difference",
        "issubset",
        "issuperset",
        "isdisjoint",
    }
)

_TUPLE_METHODS = frozenset({"count", "index"})

_STR_METHODS = frozenset(
    {
        "join",
        "split",
        "rsplit",
        "splitlines",
        "strip",
        "lstrip",
        "rstrip",
        "replace",
        "format",
        "format_map",
        "startswith",
        "endswith",
        "upper",
        "lower",
        "title",
        "capitalize",
        "casefold",
        "swapcase",
        "find",
        "rfind",
        "index",
        "rindex",
        "count",
        "encode",
        "zfill",
        "ljust",
        "rjust",
        "center",
        "partition",
        "rpartition",
        "isdigit",
        "isalpha",
        "isalnum",
        "isspace",
        "isupper",
        "islower",
        "istitle",
        "isnumeric",
        "isdecimal",
        "isidentifier",
        "isprintable",
        "isascii",
        "expandtabs",
        "removeprefix",
        "removesuffix",
        "translate",
        "maketrans",
    }
)

_PATH_METHODS = frozenset(
    {
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "exists",
        "is_file",
        "is_dir",
        "is_symlink",
        "is_absolute",
        "mkdir",
        "rmdir",
        "unlink",
        "touch",
        "rename",
        "replace",
        "resolve",
        "absolute",
        "glob",
        "rglob",
        "iterdir",
        "joinpath",
        "with_name",
        "with_suffix",
        "with_stem",
        "as_posix",
        "as_uri",
        "relative_to",
        "samefile",
        "stat",
        "lstat",
        "chmod",
        "expanduser",
    }
)

_HASH_METHODS = frozenset({"update", "digest", "hexdigest", "copy"})

_ARGUMENT_PARSER_METHODS = frozenset(
    {
        "add_argument",
        "add_argument_group",
        "add_mutually_exclusive_group",
        "add_subparsers",
        "parse_args",
        "parse_known_args",
        "parse_intermixed_args",
        "parse_known_intermixed_args",
        "set_defaults",
        "get_default",
        "print_usage",
        "print_help",
        "format_usage",
        "format_help",
        "error",
        "exit",
        "register",
    }
)

_ARGUMENT_GROUP_METHODS = frozenset(
    {"add_argument", "add_argument_group", "add_mutually_exclusive_group", "set_defaults"}
)

_CONSOLE_METHODS = frozenset(
    {
        "print",
        "print_json",
        "print_exception",
        "log",
        "rule",
        "line",
        "status",
        "input",
        "bell",
        "clear",
        "control",
        "out",
        "render",
        "render_lines",
        "render_str",
        "measure",
        "get_style",
        "begin_capture",
        "end_capture",
        "capture",
        "pager",
        "screen",
        "export_text",
        "export_html",
        "export_svg",
        "save_text",
        "save_html",
        "save_svg",
        "push_theme",
        "pop_theme",
        "use_theme",
        "push_render_hook",
        "pop_render_hook",
        "set_window_title",
        "set_alt_screen",
        "show_cursor",
        "update_screen",
        "update_screen_lines",
    }
)

_TABLE_METHODS = frozenset({"add_column", "add_row", "add_section", "grid", "get_row_style"})

# Each entry names the qualified type the target is reported under, and the methods it
# resolves. `str` and `Path` share the same shape as `list`/`dict`/`set`; nothing here reads
# an instance to decide, only the type name the caller already established. The library
# types below are keyed by their qualified name, so an annotation spelled `Table` never
# reaches them: only a constructor or a return the import binding proves does (AD-40).
_METHOD_TABLES: dict[str, tuple[str, frozenset[str]]] = {
    "list": ("builtins.list", _LIST_METHODS),
    "dict": ("builtins.dict", _DICT_METHODS),
    "set": ("builtins.set", _SET_METHODS),
    "frozenset": ("builtins.frozenset", _FROZENSET_METHODS),
    "tuple": ("builtins.tuple", _TUPLE_METHODS),
    "str": ("builtins.str", _STR_METHODS),
    "Path": ("pathlib.Path", _PATH_METHODS),
    "hashlib._Hash": ("hashlib._Hash", _HASH_METHODS),
    "argparse.ArgumentParser": ("argparse.ArgumentParser", _ARGUMENT_PARSER_METHODS),
    "argparse._ArgumentGroup": ("argparse._ArgumentGroup", _ARGUMENT_GROUP_METHODS),
    "argparse._SubParsersAction": ("argparse._SubParsersAction", frozenset({"add_parser"})),
    "rich.console.Console": ("rich.console.Console", _CONSOLE_METHODS),
    "rich.table.Table": ("rich.table.Table", _TABLE_METHODS),
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
