# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340 (PR 4.3a-4): the closed UMD envelope of the native port equals `umd_publication`.

Consumer: `native/typescript/src/umd.rs` and `umd_publication.rs`, through the test-only
`--dump-umd`. The oracle is `parse.umd_publication()`, unmodified: the name that the envelope
publishes, where, and the names that its factory writes on the global object.
"""

from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from test_collector_native_script_syntax import _mutate
from test_collector_native_syntax import ROOT, _delta, dump_binary  # noqa: F401

from archkeel.analyzer.typescript import parse

ENVELOPE = (
    '(function({f}){{if(typeof exports==="object"&&typeof module!=="undefined")'
    '{{module.exports={f}()}}else if(typeof define==="function"&&define.amd)'
    '{{define([],{f})}}else{{var {r};if(typeof window!=="undefined")'
    '{{{r}=window}}else if(typeof global!=="undefined"){{{r}=global}}'
    'else if(typeof self!=="undefined"){{{r}=self}}else{{{r}=this}}'
    "{r}.{p}={f}()}}}})"
)


def _umd(body: str, f: str = "f", r: str = "r", p: str = "Lib", args: str = "") -> str:
    return ENVELOPE.format(f=f, r=r, p=p) + f"(function({args}){{{body}}});\n"


GRID: dict[str, str] = {
    "plain": _umd("return { a: 1 };"),
    "empty": _umd(""),
    "window-write": _umd("window.X = 1; return {};"),
    "global-this-write": _umd("globalThis.Y = 2; return {};"),
    "this-write": _umd("this.Z = 3; return {};"),
    "local-write": _umd("var local = {}; local.a = 2; return local;"),
    "implicit-global": _umd("Leak = 1; return {};"),
    "implicit-member": _umd("Leak.a = 1; return {};"),
    "alias-of-window": _umd("var w = window; w.A = 1; return {};"),
    "alias-chain": _umd("var w = window; var v = w; v.B = 1; return {};"),
    "nested-write": _umd("window.A.b = 1; return {};"),
    "computed-write": _umd("window['lit'] = 1; return {};"),
    "dynamic-write": _umd("window[k] = 1; return {};"),
    "call": _umd("f(); return {};"),
    "new": _umd("new Foo(); return {};"),
    "update": _umd("count++; return {};"),
    "delete": _umd("delete window.q; return {};"),
    "for-in": _umd("for (k in o) {} return {};"),
    "catch": _umd("try { x = 1; } catch (e) { e = 2; } return {};"),
    "with": _umd("with (o) { a = 1; } return {};"),
    "arrow": _umd("var g = () => { z = 1; }; return {};"),
    "class": _umd("class K { m() { this.q = 1; } } return K;"),
    "reserved-factory": _umd("return {};", f="exports"),
    "reserved-root": _umd("return {};", r="window"),
    "same-names": _umd("return {};", f="x", r="x"),
    "names": _umd("return {};", f="factory", r="root", p="Name"),
    "escaped-name": _umd("return {};", p="a\\u0062"),
    "parameters": _umd("return {};", args="a"),
    "async": ENVELOPE.format(f="f", r="r", p="Lib") + "(async function(){});\n",
    "arrow-factory": ENVELOPE.format(f="f", r="r", p="Lib") + "(() => ({}));\n",
    "extra-statement": _umd("return {};") + "var other = 1;\n",
    "comment": "/* license */\n" + _umd("return {};") + "// end\n",
    "not-a-call": "(function(){});\n",
    "other-envelope": "(function(f){f()})(function(){});\n",
    "syntax-error": _umd("return {"),
    "empty-file": "",
}


def _python(name: str, content: bytes) -> object:
    found = parse.umd_publication(name, content)
    if found is None:
        return None
    publication, span, writes = found
    return {
        "name": publication,
        "span": {
            "line": span.line,
            "end_line": span.end_line,
            "column": span.column,
            "excerpt": span.excerpt,
        },
        "writes": None if writes is None else sorted(writes),
    }


def _native(binary: Path, files: list[tuple[str, Path]]) -> list[object]:
    request = "".join(json.dumps({"rel": rel, "file": str(path)}) + "\n" for rel, path in files)
    done = subprocess.run(
        [str(binary), "--dump-umd"],
        input=request.encode(),
        capture_output=True,
        check=False,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")[:2000]
    return [json.loads(line)["umd"] for line in done.stdout.splitlines()]


def _check(tmp_path: Path, binary: Path, sources: dict[str, str], suffix: str = ".js") -> int:
    files = []
    for name, text in sources.items():
        path = tmp_path / f"{name}{suffix}"
        path.write_text(text, encoding="utf-8")
        files.append((f"src/{path.name}", path))
    found = _native(binary, files)
    differences = []
    published = 0
    for (rel, path), native in zip(files, found, strict=True):
        python = _python(rel, path.read_bytes())
        published += python is not None
        differences += list(_delta(rel, native, python))[:3]
    assert differences == [], "\n".join(differences[:20])
    return published


def test_the_grid_equals_umd_publication(tmp_path: Path, dump_binary: Path) -> None:  # noqa: F811
    published = _check(tmp_path, dump_binary, GRID)
    # Most of the grid is a closed envelope, and some of it is not.
    assert 15 < published < len(GRID)


def test_a_module_or_a_typescript_file_publishes_nothing(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
) -> None:
    for suffix in (".ts", ".mjs", ".cjs"):
        folder = tmp_path / suffix[1:]
        folder.mkdir()
        assert _check(folder, dump_binary, {"a": GRID["plain"]}, suffix) == 0


def test_mutated_envelopes_equal_umd_publication(tmp_path: Path, dump_binary: Path) -> None:  # noqa: F811
    rng = random.Random(4_3_4_1)
    sources = {
        f"m{index}": _mutate(rng, text)
        for index, text in enumerate(text for _ in range(10) for text in GRID.values() if text)
    }
    _check(tmp_path, dump_binary, sources)
