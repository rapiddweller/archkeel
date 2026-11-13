# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa: E402
"""Compare the definition binding inputs before import convergence (AD-396)."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest
from oracle_support import ORACLE_UNAVAILABLE

pytest.skip(ORACLE_UNAVAILABLE, allow_module_level=True)
from archkeel.analyzer.python.bindings import collect_bindings
from archkeel.analyzer.python.symbols import (
    _class_is_frozen,
    _default_constructor_body,
    _static_enum_members,
)
from first_difference import same
from python_binding_costs import COSTS
from test_collector_native_python_parse import _minor
from test_collector_native_python_scope import _FIXTURES

from archkeel.analyzer.python import source as s


def _same(found: Any, expected: Any, label: object) -> None:
    same(
        json.dumps(found, sort_keys=True, ensure_ascii=False),
        json.dumps(expected, sort_keys=True, ensure_ascii=False),
        label,
    )


def _python(root: Path, rel: str) -> dict[str, Any] | None:
    namespace = Path(rel).parts[0].removesuffix(".py")
    parsed = s.parse_sources([root / rel], root=root, namespace=namespace)
    if not parsed.modules:
        return None
    m = parsed.modules[0]
    nodes = m.all_nodes[1:]
    scope = m.scope_nodes[1:]
    evidence: dict[str, Any] = {}
    records = collect_bindings([m], evidence)
    owners = s.function_class_owners(m.tree, m.module)
    definitions = []
    for n in nodes:
        if not isinstance(n, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        own = tuple(s.own_scope(n))
        item: dict[str, Any] = {
            "name": n.name,
            "line": n.lineno,
            "own": [type(c).__name__ for c in own],
            "lexical": sorted(s.lexical_binding_names(n)),
        }
        if isinstance(n, ast.ClassDef):
            item.update(
                expressions=[s.annotation_text(e) for e in s.class_definition_expressions(n)],
                enum=_static_enum_members(n),
                frozen=[_class_is_frozen(n, m, allow_pydantic=b) for b in (False, True)],
                default_body=_default_constructor_body(n),
            )
        else:
            item["class_owner"] = owners.get(id(n))
        definitions.append(item)
    queries = []
    for name in ("object", "alias", "property", "x"):
        queries.append(
            [s.binding_may_exist_before(m, m.tree.body, None, name)]
            + [
                result
                for stop in (*m.tree.body[:1], *m.tree.body[-1:])
                for result in (
                    s.bound_once_before(m.tree.body, stop, name),
                    s.binding_may_exist_before(m, m.tree.body, stop, name),
                )
            ]
        )
    flags = [
        [
            s.exposes_dynamic_namespace(
                m, n, local_namespace=local, member_surface=member, include_import_effects=imports
            )
            for local in (False, True)
            for member in (False, True)
            for imports in (False, True)
        ]
        for n in nodes
    ]
    parents = {c: p for p in ast.walk(m.tree) for c in ast.iter_child_nodes(p)}
    return {
        "bound": list(m.bound_names),
        "scope": [type(n).__name__ for n in scope],
        "scope_bound": list(m.scope_bound_names),
        "events": [
            [type(n).__name__, *s.location(n), name] for n, name in s.module_scope_bindings(m)
        ],
        "definitions": definitions,
        "queries": queries,
        "flags": flags,
        "own_only": [s.exposes_own_namespace_only(m, n) for n in nodes],
        "read_names": [s.reads_only_namespace_names(m, n, parents) for n in nodes],
        "rebind": [s._namespace_may_rebind(m, include_import_effects=b) for b in (False, True)],
        "bindings": records,
        "evidence": sorted(evidence.values(), key=lambda e: e["id"]),
        "statement_bindings": [
            s._class_statement_bindings(n) for n in nodes if isinstance(n, ast.stmt | ast.NamedExpr)
        ],
        "closures": [
            sorted(s.member_binding_closure(nodes, {root}, member_surface=member))
            for member in (False, True)
            for root in ("alias", "object", "x")
        ],
        "configured_closure": sorted(
            s.member_binding_closure(
                nodes,
                {"x"},
                member_surface=True,
                contained={("x", "alias")},
                local_references={n for n in nodes if isinstance(n, ast.Name) and n.id == "local"},
                namespace_owners={"alias"},
                namespace_bindings=set(m.scope_bound_names),
            )
        ),
    }


def _native_rows(binary: Path, root: Path, paths: list[str]) -> Iterator[dict[str, Any]]:
    with tempfile.TemporaryFile(mode="w+") as source, tempfile.TemporaryFile(mode="w+") as errors:
        source.writelines(f"{path}\n" for path in paths)
        source.seek(0)
        process = subprocess.Popen(
            [str(binary), "--dump-bindings", str(_minor()), str(root)],
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                yield json.loads(line)
            code = process.wait(timeout=45)
            errors.seek(0)
            assert code == 0, errors.read()
        finally:
            if process.returncode is None:
                process.kill()
                process.wait()
            if process.stdout is not None:
                process.stdout.close()


def _native(binary: Path, root: Path, paths: list[str]) -> list[dict[str, Any]]:
    return list(_native_rows(binary, root, paths))


def test_the_binding_dump_exists(tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text("def f(x):\n    y = 1\n    return 2\n")
    found = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    _same(found["data"], _python(tmp_path, "probe.py"), "binding primitives")


@pytest.mark.parametrize("name", COSTS)
def test_binding_loop_cost(name: str, tmp_path: Path, python_dump_binary: Path) -> None:
    text, work = COSTS[name]
    (tmp_path / "probe.py").write_text(text)
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert row["full_scope"], row.get("gap")
    assert row["work"] == work


@pytest.mark.parametrize("index", range(160))
def test_generated_binding_probe(index: int, tmp_path: Path, python_dump_binary: Path) -> None:
    fragments = (
        "x = 1\ndel x\n",
        "import os.path\nfrom a import b as alias\n",
        "if q:\n    x = 1\nelse:\n    def x(): pass\n",
        "try:\n    x = 1\nexcept ValueError as alias:\n    pass\n",
        "x = [i for i in y if (alias := i)]\n",
        "class C:\n    x: bool\n    A = 1\n    B = 2\n    def f(self, p):\n        y = p\n",
        "def f(a, /, b=1, *c, d=2, **e):\n    x = a\n    del b\n",
        "def outer(x):\n    def inner(y): return x\n    return inner\n",
        "globals().keys()\nlist(globals())\n'x' in globals()\n",
        "locals()\nvars(x)\nexec('x = 1')\n__import__('x')\n",
        "match q:\n    case {'x': x, **alias}: pass\n    case [*rest]: pass\n",
        "class C:\n    @property\n    def x(self): return 1\n"
        "    @x.setter\n    def x(self, v): pass\n",
        "class C:\n    def __new__(cls): return object()\n",
        "class C:\n    _ignore_ = 'A'\n    A = 1\n",
        "class C:\n    def f(self):\n        class D:\n            def g(self): pass\n",
        "def f():\n    global x\n    x = lambda y: y\n",
    )
    text = (
        fragments[index % len(fragments)]
        + fragments[(index // len(fragments) + 3) % len(fragments)]
    )
    (tmp_path / "probe.py").write_text(text)
    found = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    expected = _python(tmp_path, "probe.py")
    if expected is not None:
        assert found["full_scope"], found
        _same(found["data"], expected, index)


@pytest.mark.parametrize(
    "text",
    (
        "__annotations__\nf.f_globals\nf.f_locals\nf.f_builtins\ntyping.get_type_hints(x)\n",
        "import dataclasses\n@dataclasses.dataclass(frozen=True)\nclass C:\n    x: int\n",
        "class C:\n    model_config = pydantic.ConfigDict(frozen=True)\n",
        "x = y\ny = z.attr\nlocal = x\nx = local\n",
        "def f():\n    return set(globals().keys().keys())\n",
        "set = custom\nlist = other\nlist(globals())\n",
        "type A[T = int] = list[T]\nclass C[T]:\n    def f[U](self, x: U): ...\n",
        "def f[T: x](x):\n    return 1\n",
        "def f[T = x](x):\n    return 1\n",
        "def f():\n    def inner(x):\n        nonlocal f\n        return f\n",
        "class C:\n    A = B = 1\n    del A\n    B = 2\n    C: int = 3\n",
        "class C:\n    @overload\n    def f(self): ...\n    _local = lambda x: x\n",
        "class C:\n    def f(self, x: int = 1) -> int: ...\n",
        "class C:\n    async def f(self): pass\n    A = None\n",
        "@dec\n# A comment after the decorator.\nclass C:\n    def f(self): pass\n",
        "class C:\n    x = '\\u2028'\n    y = 'é'\n",
        "x = {k: v for k, v in things}\nf = lambda x=1: x\n",
        "from a import *\nclass C:\n    from b import *\n",
    ),
)
def test_binding_edge(text: str, tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(text)
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    expected = _python(tmp_path, "probe.py")
    if expected is not None and row["full_scope"]:
        _same(row["data"], expected, "binding edge")
    else:
        assert row.get("gap"), row


def _compare(binary: Path, root: Path) -> tuple[int, int, int, int]:
    paths = sorted(
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if p.is_file() and not p.is_symlink() and ".venv" not in p.parts
    )
    assert paths, "binding corpus has no Python files"
    counts = [len(paths), 0, 0, 0]
    minor = _minor()
    shared_refusals = 0
    gaps: Counter[str] = Counter()
    for row in _native_rows(binary, root, paths):
        if report := os.environ.get("ARCHKEEL_BINDING_WORK_REPORT"):
            private = root.name.startswith("priv")
            record = {
                "minor": minor,
                "corpus": "private aggregate" if private else root.name,
                "file": "private aggregate" if private else row["file"],
                "work": row["work"],
                "gap": row.get("gap"),
            }
            with Path(report).open("a") as stream:
                stream.write(json.dumps(record) + "\n")
        assert row["work"] * 4 <= 64_000_000, "binding corpus work has less than a fourfold margin"
        expected = _python(root, row["file"])
        if expected is None:
            assert not row["full_scope"], row["file"]
            shared_refusals += 1
            counts[1] += 1
        elif not row["full_scope"]:
            assert row["gap"], row
            counts[2] += 1
            gaps[row["gap"]] += 1
        else:
            _same(row["data"], expected, row["file"])
            counts[1] += 1
    assert counts[1] + counts[2] == counts[0]
    if shared_refusals or gaps:
        print(f"binding refusals {_minor()}: shared={shared_refusals}, stricter={dict(gaps)}")
    files, equal, stricter, different = counts
    return files, equal, stricter, different


def test_an_empty_corpus_has_a_named_failure(tmp_path: Path, python_dump_binary: Path) -> None:
    with pytest.raises(AssertionError, match="binding corpus has no Python files"):
        _compare(python_dump_binary, tmp_path)


def _owner_source(definitions: int, width: int = 3000) -> str:
    classes = "".join(
        "    " * depth + f"class C{depth}" + "x" * width + ":\n" for depth in range(90)
    )
    return classes + ("    " * 90 + "def f(): pass\n") * definitions


def _measured_dump(binary: Path, root: Path, output: Path) -> tuple[dict[str, Any], float, int]:
    if sys.platform == "darwin":
        flags, pattern, unit = ["-l"], r"(\d+)\s+maximum resident set size", 1
    elif sys.platform.startswith("linux"):
        flags, pattern, unit = ["-v"], r"Maximum resident set size \(kbytes\):\s*(\d+)", 1024
    else:
        pytest.skip("the owner memory check needs POSIX time")
    start = perf_counter()
    with output.open("w") as stream:
        result = subprocess.run(
            ["/usr/bin/time", *flags, str(binary), "--dump-bindings", str(_minor()), str(root)],
            input="probe.py\n",
            text=True,
            stdout=stream,
            stderr=subprocess.PIPE,
            timeout=45,
            check=True,
        )
    elapsed = perf_counter() - start
    assert output.stat().st_size <= 32 * 1024 * 1024, "binding output exceeds its byte limit"
    found = re.search(pattern, result.stderr)
    assert found, result.stderr
    return json.loads(output.read_text()), elapsed, int(found[1]) * unit


def test_large_owner_output_is_a_named_gap(tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(_owner_source(500, 1000))
    row, elapsed, peak = _measured_dump(python_dump_binary, tmp_path, tmp_path / "output.json")
    assert not row["full_scope"]
    assert row["gap"] == "binding output limit exceeded (33554432 bytes)"
    assert "data" not in row
    assert peak < 512 * 1024 * 1024
    print({"owner_gap_work": row["work"], "seconds": elapsed, "peak_bytes": peak})


def test_nested_owner_work_time_and_memory_scale_with_input(
    tmp_path: Path,
    python_dump_binary: Path,
) -> None:
    sizes, times, peaks, works = [], [], [], []
    for definitions in (1000, 3000):
        text = _owner_source(definitions)
        sizes.append(len(text.encode()))
        (tmp_path / "probe.py").write_text(text)
        row, elapsed, peak = _measured_dump(python_dump_binary, tmp_path, tmp_path / "output.json")
        assert not row["full_scope"]
        assert row["gap"] == "binding output limit exceeded (33554432 bytes)"
        assert "data" not in row
        times.append(elapsed)
        peaks.append(peak)
        works.append(row["work"])
        print(
            {"input_bytes": sizes[-1], "work": row["work"], "seconds": elapsed, "peak_bytes": peak}
        )
    ratio = sizes[1] / sizes[0]
    assert times[1] / times[0] < ratio * 3
    assert peaks[1] / peaks[0] < ratio * 2
    assert max(peaks) < 512 * 1024 * 1024
    assert works[1] / works[0] < ratio * 2


@pytest.mark.parametrize("fixture", (*_FIXTURES, "fixtures"))
def test_fixture_binding_inputs(fixture: str, python_dump_binary: Path) -> None:
    counts = _compare(python_dump_binary, Path(__file__).parents[1] / fixture)
    print(f"binding parity fixture {_minor()}: {counts}")


@pytest.mark.skipif(not os.environ.get("ARCHKEEL_BINDING_CORPORA"), reason="no corpus is named")
def test_corpus_binding_inputs(python_dump_binary: Path) -> None:
    total = [0, 0, 0, 0]
    for index, root in enumerate(os.environ["ARCHKEEL_BINDING_CORPORA"].split(os.pathsep), 1):
        counts = _compare(python_dump_binary, Path(root))
        print(f"binding parity corpus {index} {_minor()}: {counts}")
        total = [a + b for a, b in zip(total, counts, strict=True)]
    print(f"binding parity corpus {_minor()}: {total}")


@pytest.mark.parametrize("names_only", (False, True))
def test_binding_work_scales_linearly(
    tmp_path: Path, python_dump_binary: Path, names_only: bool
) -> None:
    works, times = [], []
    for size in (800, 2400):
        text = (
            "list(globals())\n" * size
            if names_only
            else "".join(f"def f{i}(p):\n    local = 1\n    return p\n" for i in range(size))
        )
        (tmp_path / "probe.py").write_text(text)
        start = perf_counter()
        row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
        times.append(perf_counter() - start)
        assert row["full_scope"], row.get("gap")
        works.append(row["work"])
    assert 2.8 < works[1] / works[0] < 3.2
    assert times[1] / times[0] < 7


def test_binding_work_exhaustion_is_a_named_gap(tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(_owner_source(1, 8000))
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert not row["full_scope"]
    assert row["gap"] == "binding work limit exceeded"
    assert "data" not in row


@pytest.mark.parametrize("functions", (False, True))
def test_large_ordinary_files_keep_a_fourfold_work_margin(
    functions: bool,
    tmp_path: Path,
    python_dump_binary: Path,
) -> None:
    text = (
        "".join(f"def f{i}(p):\n    return p\n" for i in range(5000))
        if functions
        else "".join(f"v{i} = {i}\n" for i in range(10000))
    )
    (tmp_path / "probe.py").write_text(text)
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert row["full_scope"], row.get("gap")
    assert row["work"] * 4 <= 64_000_000
