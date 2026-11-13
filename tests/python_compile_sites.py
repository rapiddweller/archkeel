# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read CPython source data. Never import, build or execute the downloaded sources.

This inventory is deliberately not a completeness certificate. Dynamic messages,
allocation failures and the reachability of AST-only checks need manual analysis.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

TAGS = {"3.11": "3.11.12", "3.12": "3.12.13", "3.13": "3.13.15", "3.14": "3.14.7"}
FILES = (
    "Python/compile.c",
    "Python/codegen.c",
    "Python/symtable.c",
    "Python/future.c",
    "Python/ast.c",
    "Python/ast_opt.c",
    "Python/assemble.c",
    "Python/flowgraph.c",
    "Parser/action_helpers.c",
    "Parser/pegen.c",
    "Parser/pegen_errors.c",
    "Parser/string_parser.c",
    "Parser/tokenizer.c",
    "Grammar/python.gram",
)
CALL = re.compile(
    r"\b(?:compiler_error|_PyCompile_Error|_PyErr_RaiseSyntaxError|"
    r"PyErr_(?:Format|SetString|SetObject|NoMemory)|"
    r"_PyPegen_raise_error\w*|_PyTokenizer_(?:syntaxerror|indenterror)|"
    r"RAISE_(?:SYNTAX|INDENTATION)_ERROR\w*|RAISE_ERROR\w*|"
    r"RETURN_SYNTAX_ERROR|PyUnicode_AsUTF8AndSize|(?:_Py|Py)_EnterRecursiveCall\w*)\s*\("
)
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*', re.S)
STRING = re.compile(r'"(?:\\.|[^"\\])*"')
EXCEPTIONS = {
    "SyntaxError",
    "IndentationError",
    "TabError",
    "ValueError",
    "OverflowError",
    "RecursionError",
    "MemoryError",
    "UnicodeEncodeError",
    "UnicodeDecodeError",
}


def _comments(text: str) -> str:
    return TOKEN.sub(
        lambda m: (
            "".join("\n" if c == "\n" else " " for c in m[0])
            if m[0].startswith(("/*", "//"))
            else m[0]
        ),
        text,
    )


def _call_end(text: str, start: int) -> int:
    depth = 1
    cursor = start
    while cursor < len(text):
        token = TOKEN.match(text, cursor)
        if token:
            cursor = token.end()
            continue
        char = text[cursor]
        depth += (char == "(") - (char == ")")
        if not depth:
            return cursor
        cursor += 1
    raise ValueError(f"unclosed C call at {start}")


def _strings(text: str) -> list[str]:
    groups = re.findall(r'"(?:\\.|[^"\\])*"(?:\s*"(?:\\.|[^"\\])*")*', text)
    return ["".join(ast.literal_eval(token) for token in STRING.findall(group)) for group in groups]


def inventory(root: Path) -> dict[str, Any]:
    pins: dict[str, Any] = {}
    for minor, tag in TAGS.items():
        base = root / tag
        files = {base / name for name in FILES if (base / name).is_file()}
        for directory in ("Parser/tokenizer", "Parser/lexer"):
            files.update((base / directory).glob("*.c"))
        sites: list[dict[str, Any]] = []
        digests = {}
        for path in sorted(files):
            rel = path.relative_to(base).as_posix()
            raw = path.read_bytes()
            digests[rel] = hashlib.sha256(raw).hexdigest()
            text = _comments(raw.decode())
            functions = list(re.finditer(r"^([A-Za-z_]\w*)\([^;]*?\)\s*\n\{", text, re.M))
            rules = list(re.finditer(r"^(\w+)(?:\[[^\n]*?\])?(?:\([^\n]*?\))?:", text, re.M))
            constants = {
                m[1]: _strings(m[2])
                for m in re.finditer(r"^#define\s+(\w+)\s+((?:\\\n|[^\n])*)", text, re.M)
            }
            for match in CALL.finditer(text):
                # A function declaration is not a raise site.
                end = _call_end(text, match.end())
                if text[end + 1 :].lstrip().startswith("{"):
                    continue
                args = text[match.end() : end]
                kinds = set(re.findall(r"PyExc_(\w+)", args))
                if kinds and not kinds & EXCEPTIONS:
                    continue
                owner = [
                    m[1]
                    for m in (rules if rel.endswith(".gram") else functions)
                    if m.start() <= match.start()
                ]
                messages = _strings(args)
                for name in re.findall(r"\b[A-Z_]{3,}\b", args):
                    messages.extend(constants.get(name, []))
                line = text.count("\n", 0, match.start()) + 1
                column = match.start() - text.rfind("\n", 0, match.start())
                sites.append(
                    {
                        "id": f"{minor}:{rel}:{line}:{column}",
                        "file": rel,
                        "line": line,
                        "function": owner[-1] if owner else "<macro>",
                        "call": match[0].split("(")[0].strip(),
                        "messages": list(dict.fromkeys(messages)),
                        "expression": " ".join(args.split()),
                    }
                )
        pins[minor] = {"tag": f"v{tag}", "source_sha256": digests, "sites": sites}
    return pins


def message_pattern(message: str) -> str:
    parts = re.split(r"(%(?:[.\d+\-#]*)(?:z|l|ll)?[sURArdicuxX%])", message)
    return "".join(".*" if part.startswith("%") else re.escape(part) for part in parts)


def witnesses(
    binary: Path, minor: str, pins: dict[str, Any], sources: list[str]
) -> list[dict[str, Any]]:
    """A message witness is not a proof that every path to a C site is covered."""
    refused = []
    for source in sorted(set(sources), key=lambda text: (len(text), text)):
        try:
            compile(source, "p.py", "exec", dont_inherit=True)
        except (
            SyntaxError,
            ValueError,
            OverflowError,
            RecursionError,
            MemoryError,
            UnicodeError,
        ) as error:
            refused.append((source, getattr(error, "msg", str(error)), type(error).__name__))
    with tempfile.TemporaryDirectory(prefix="archkeel-compile-sites-") as directory:
        root = Path(directory)
        for index, (source, _, _) in enumerate(refused):
            (root / f"r{index}.py").write_text(source)
        done = subprocess.run(
            [str(binary), "--dump", minor.split(".")[1], str(root)],
            input="".join(f"r{index}.py\n" for index in range(len(refused))),
            text=True,
            capture_output=True,
            check=True,
        )
    native = {
        row["file"]: row["outcome"]
        for line in done.stdout.split("\n")
        if line
        for row in [json.loads(line)]
    }
    rows = []
    for site in pins[minor]["sites"]:
        matches = [
            index
            for index, (_, message, exception) in enumerate(refused)
            if any(re.fullmatch(message_pattern(fmt), message) for fmt in site["messages"])
            or (site["function"] == "_PyCompile_CleanDoc" and exception == "UnicodeEncodeError")
        ]
        index = matches[0] if matches else None
        found = native[f"r{index}.py"] if index is not None else None
        if index is not None and found is None:
            raise ValueError(
                f"native accepts a CPython refusal: {site['id']} {refused[index][0]!r}"
            )
        row = {
            "site": site["id"],
            "minor": minor,
            "status": "REFUSED" if index is not None else "UNPROVED",
            "source": refused[index][0] if index is not None else None,
            "reason": found["message"]
            if found
            else "No source witness; reachability is not proved.",
        }
        if found:
            row["exception"] = refused[index][2]
            row["compiler_message"] = refused[index][1]
            row["native_check"] = native_check(found["message"])
        rows.append(row)
    return rows


def native_check(reason: str) -> str:
    root = Path(__file__).parents[1]
    for path in sorted((root / "native/python/src").rglob("*.rs")):
        for line, text in enumerate(path.read_text().splitlines(), 1):
            if f'"{reason}"' in text:
                return f"{path.relative_to(root)}:{line}"
    path = root / "native/python/src/parse.rs"
    line = next(
        index
        for index, text in enumerate(path.read_text().splitlines(), 1)
        if text.startswith("fn first_parser_error")
    )
    return f"native/python/src/parse.rs:{line}"


if __name__ == "__main__":
    import argparse
    import sys

    from python_refusal_probes import edge_probes
    from test_collector_native_python_compiler import SOURCES
    from test_collector_native_python_parse import _minor

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path)
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    if sys.getrecursionlimit() != 1000:
        raise ValueError("the compile oracle requires the default recursion limit of 1000")
    root = Path(__file__).parents[1]
    pins = inventory(args.sources)
    reviewed = json.loads((root / "tests/python_compile_refusals.json").read_text())["sources"]
    sources = [row["source"] for row in reviewed if isinstance(row["source"], str)]
    sources += list(edge_probes().values()) + list(SOURCES.values())
    print(json.dumps(witnesses(args.binary.resolve(), f"3.{_minor()}", pins, sources), indent=2))
