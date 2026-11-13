# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa: E402
"""Compare the import-local proofs needed by member convergence (AD-404)."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import tempfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest
from oracle_support import ORACLE_UNAVAILABLE

pytest.skip(ORACLE_UNAVAILABLE, allow_module_level=True)
from archkeel.analyzer.python.imports import collect_imports
from first_difference import same
from python_proof_costs import COSTS, EXTRA_COSTS
from test_collector_native_python_parse import _minor
from test_collector_native_python_scope import _FIXTURES

from archkeel.analyzer.python import source as s


def _python(root: Path, rel: str) -> dict[str, Any] | None:
    namespace = Path(rel).parts[0].removesuffix(".py")
    parsed = s.parse_sources([root / rel], root=root, namespace=namespace)
    if not parsed.modules:
        return None
    module = parsed.modules[0]
    collect_imports([module], {module.module}, {}, namespace=namespace)
    methods, classes, expressions, aliases, generics = [], [], [], [], []
    for node in module.all_nodes[1:]:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            methods.append([node.lineno, s.method_decorator_data(module, node, None)])
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    methods.append([child.lineno, s.method_decorator_data(module, child, node)])
            classes.append(
                [
                    node.lineno,
                    {
                        "header": s.class_header_static(node),
                        "exposed": s.class_body_exposes_namespace(module, node),
                        "unproven": [
                            s.unproven_class_body(module, node, inert_values=b)
                            for b in (False, True)
                        ],
                        "receives": s._class_members_receive_owner(module, node),
                        "namespace": s.class_namespace_static(module, node),
                        "native_body": s._native_class_body_static(module, node),
                    },
                ]
            )
            generics.append([node.lineno, s.generic_parameters(module, node)])
        if isinstance(node, ast.Name | ast.Attribute | ast.Subscript | ast.BinOp):
            expressions.append(
                [
                    node.lineno,
                    node.col_offset,
                    s.resolve_static_name(module, node),
                    s.is_static_type_alias_value(module, node),
                ]
            )
        if (
            isinstance(node, ast.stmt)
            and (value := s.admitted_type_alias_value(module, node)) is not None
        ):
            aliases.append([node.lineno, s.annotation_text(value)])
    return {
        "stable": sorted(s.stable_direct_module_bindings(module)),
        "stable_without_imports": sorted(
            s.stable_direct_module_bindings(module, include_import_effects=False)
        ),
        "unique": sorted(s.unique_direct_module_bindings(module)),
        "methods": methods,
        "classes": classes,
        "types": {
            "expressions": expressions,
            "aliases": aliases,
            "generics": generics,
            "nullable": sorted(s.intrinsic_nullable_aliases(module)),
            "setters": sorted([*s.location(n)] for n in s.setter_local_references(module)),
        },
    }


def _same(found: object, expected: object, label: object) -> None:
    same(
        json.dumps(found, sort_keys=True, ensure_ascii=False),
        json.dumps(expected, sort_keys=True, ensure_ascii=False),
        label,
    )


def _native(binary: Path, root: Path, paths: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(
        [str(binary), "--dump-proofs", str(_minor()), str(root)],
        input="".join(f"{path}\n" for path in paths),
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    )
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_import_local_proof_dump_exists(tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(
        "from builtins import staticmethod as static\nclass C:\n    @static\n    def f(): pass\n"
    )
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert row["full_scope"], row
    assert row["data"]["stable"] == ["C", "static"]
    _same(row["data"], _python(tmp_path, "probe.py"), "proof dump")


FRAGMENTS = (
    "from builtins import staticmethod as static, property as prop\n"
    "class C:\n    @static\n    def f(): pass\n",
    "class C:\n    @property\n    def x(self): return 1\n"
    "    @x.setter\n    def x(self, x): self.x = x\n",
    "class C(Base):\n    @Base.x.getter\n    def x(self): return 2\n",
    "from typing import Generic, TypeVar\nT = TypeVar('T')\nclass C(Generic[T]): pass\n",
    "from typing import Optional as Opt, TypeAlias\nA: TypeAlias = str | None\nB = Opt[str]\n",
    "import builtins as b\nclass C:\n    @b.classmethod\n    def f(cls): pass\n",
    "class C:\n    x = lambda: 1\n    _f = lambda: 2\n    x: int\n",
    "class C:\n    __module__: str\n    A = {'a': (1, 2)}\n    _x = -2.5\n",
    "class C:\n    @staticmethod\n    @classmethod\n    def f(cls): pass\n",
    "class C:\n    def f(self): pass\n    def f(self): pass\n",
    "class C:\n    def f(self): pass\n    if guard:\n        f = other\n",
    "from builtins import globals as g\ng()\nclass C: pass\n",
    "import os.path as p\nx = p\nx.attr = 2\nfrom os.path import join\n",
    "class C:\n    _f = lambda a=(1, 2): a\n    z = {[]: 2}\n",
    "class C:\n    @property\n    def x(self): pass\n    @x.deleter\n    def x(self): pass\n",
    "class C:\n    @property\n    def x(self): pass\n    @x.setter\n"
    "    def x(self, x):\n        return [x for x in x]\n",
)

EXTRA = (
    "import builtins as b\nx = b.foo() + 1\n",
    "from ...os import path as x\n",
    "def f():\n    global x\n    x = 1\n",
    "from __future__ import annotations\n"
    "class C:\n    def f(self, x: int, *args: str, **kw: bool) -> int: pass\n",
    "class C(B.D):\n    @B.D.x.getter\n    def x(self): return 1\n",
    "class C:\n    @property\n    def x(self): return 1\n"
    "    @x.setter\n    def x(self, x):\n        global other\n        return x\n",
    "class C:\n    x = {'x': (1, [2])}\n    y = {1, 2}\n    z = -1 + 2j\n",
    "class C:\n    x = (y := 1)\n    _f = lambda x=1: x\n",
)


@pytest.mark.parametrize("index", range(256 + len(EXTRA)))
def test_generated_proof(index: int, tmp_path: Path, python_dump_binary: Path) -> None:
    text = FRAGMENTS[index % 16] + FRAGMENTS[index // 16] if index < 256 else EXTRA[index - 256]
    (tmp_path / "probe.py").write_text(text)
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    expected = _python(tmp_path, "probe.py")
    assert expected is not None
    assert row["full_scope"], row
    assert row["work"] == (COSTS[index] if index < 256 else EXTRA_COSTS[index - 256])
    _same(row["data"], expected, index)


def _rows(binary: Path, root: Path, paths: list[str]) -> Iterator[dict[str, Any]]:
    with tempfile.TemporaryFile(mode="w+") as source, tempfile.TemporaryFile(mode="w+") as errors:
        source.writelines(f"{p}\n" for p in paths)
        source.seek(0)
        process = subprocess.Popen(
            [str(binary), "--dump-proofs", str(_minor()), str(root)],
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                yield json.loads(line)
            code = process.wait(timeout=30)
            errors.seek(0)
            assert code == 0, errors.read()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()


def _compare(binary: Path, root: Path) -> tuple[int, int, int, int]:
    paths = sorted(
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if p.is_file() and not p.is_symlink() and ".venv" not in p.parts
    )
    assert paths, "proof corpus has no Python files"
    equal = 0
    stricter: Counter[str] = Counter()
    for row in _rows(binary, root, paths):
        expected = _python(root, row["file"])
        if expected is None:
            assert not row["full_scope"], row["file"]
            equal += 1
        elif not row["full_scope"]:
            assert row["gap"], row["file"]
            stricter[row["gap"]] += 1
        else:
            _same(row["data"], expected, row["file"])
            equal += 1
        if report := os.environ.get("ARCHKEEL_PROOF_WORK_REPORT"):
            private = root.name.startswith("priv")
            with Path(report).open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "minor": _minor(),
                            "corpus": "private aggregate" if private else root.name,
                            "file": "private aggregate" if private else row["file"],
                            "work": row["work"],
                            "gap": row.get("gap"),
                        }
                    )
                    + "\n"
                )
    assert equal + sum(stricter.values()) == len(paths)
    print(f"proof stricter {_minor()}: {dict(stricter)}")
    return len(paths), equal, sum(stricter.values()), 0


@pytest.mark.parametrize("fixture", (*_FIXTURES, "fixtures"))
def test_fixture_proofs(fixture: str, python_dump_binary: Path) -> None:
    print(
        "proof fixture parity",
        _minor(),
        fixture,
        _compare(python_dump_binary, Path(__file__).parents[1] / fixture),
    )


@pytest.mark.skipif(not os.environ.get("ARCHKEEL_PROOF_CORPORA"), reason="no corpus is named")
def test_corpus_proofs(python_dump_binary: Path) -> None:
    total = [0, 0, 0, 0]
    for index, root in enumerate(os.environ["ARCHKEEL_PROOF_CORPORA"].split(os.pathsep)):
        counts = _compare(python_dump_binary, Path(root))
        print("proof corpus parity", _minor(), index, counts)
        total = [a + b for a, b in zip(total, counts, strict=True)]
    print("proof total parity", _minor(), total)


def test_empty_corpus(tmp_path: Path, python_dump_binary: Path) -> None:
    with pytest.raises(AssertionError, match="proof corpus has no Python files"):
        _compare(python_dump_binary, tmp_path)


def test_proof_output_limit_keeps_no_partial_table(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    text = (".".join(["a" * 1000] * 40) + "\n") * 45
    (tmp_path / "probe.py").write_text(text)
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert row == {
        "file": "probe.py",
        "full_scope": False,
        "gap": "binding output limit exceeded (33554432 bytes)",
        "work": 458304,
    }


@pytest.mark.parametrize(
    "raw",
    (
        b"x = " + b"(" * 5000 + b"1" + b")" * 5000,
        b"x = '" + b"x" * 1_000_000 + b"'\n",
        b"x = 1\n" * 100_000,
        b"x = 1\x00\n",
        b"x = '\xff'\n",
    ),
)
def test_hostile_proof_input(raw: bytes, tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_bytes(raw)
    start = perf_counter()
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    elapsed = perf_counter() - start
    assert elapsed < 5
    assert isinstance(row["full_scope"], bool)
    if not row["full_scope"]:
        assert row["gap"] and "data" not in row
    print("hostile proof", len(raw), elapsed, row.get("gap"))


def test_proof_time_and_memory_scale(tmp_path: Path, python_dump_binary: Path) -> None:
    import re
    import sys

    if sys.platform == "darwin":
        flags, pattern, unit = ["-l"], r"(\d+)\s+maximum resident set size", 1
    elif sys.platform.startswith("linux"):
        flags, pattern, unit = ["-v"], r"Maximum resident set size \(kbytes\):\s*(\d+)", 1024
    else:
        pytest.skip("peak memory measurement needs POSIX time")
    works, times, peaks = [], [], []
    for size in (1000, 3000):
        (tmp_path / "probe.py").write_text(
            "".join(f"class C{i}:\n    @staticmethod\n    def f(): pass\n" for i in range(size))
        )
        with tempfile.TemporaryFile(mode="w+") as output:
            start = perf_counter()
            result = subprocess.run(
                [
                    "/usr/bin/time",
                    *flags,
                    str(python_dump_binary),
                    "--dump-proofs",
                    str(_minor()),
                    str(tmp_path),
                ],
                input="probe.py\n",
                text=True,
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=15,
            )
            times.append(perf_counter() - start)
            output.seek(0)
            row = json.load(output)
        assert row["full_scope"], row.get("gap")
        works.append(row["work"])
        match = re.search(pattern, result.stderr)
        assert match, result.stderr
        peaks.append(int(match[1]) * unit)
    print("proof scaling", {"work": works, "seconds": times, "peak_bytes": peaks})
    assert 2.8 < works[1] / works[0] < 3.2
    assert times[1] / times[0] < 6
    assert peaks[1] / peaks[0] < 5
    assert max(peaks) < 512 * 1024 * 1024
