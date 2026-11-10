# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340 (PR 4.3a-5): the script dependencies cost time that grows linearly with the project.

Consumer: `native/typescript/src/script_*.rs`. Python asks "does any other file publish, bind or
write this name" with a loop over the project for each use of a global. The native analysis answers
from indexes, so a project with n files that publish and n uses must cost twice as much for 2n.
Each shape is a project. The tests compare it with the Python collector at small sizes and bound
the ratio of the CPU time of 2n to n on the real collector.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from collector_timing import Taken, interleaved_least, timed_run
from test_collector_native_imports import _differences, _request
from test_collector_native_scaling import (
    CAP,
    CONFIG,
    collector,  # noqa: F401
    timing_for_profile,
)
from test_collector_native_scaling import (
    _request as wire_request,
)
from test_collector_native_script_scaling import SCRIPT_RATIO

Files = dict[str, str]


def _each(template: str, n: int) -> str:
    return "\n".join(template.replace("{i}", str(i)) for i in range(n))


def _publishers(n: int) -> Files:
    files = {f"p{i}.js": f"function run{i}() {{}}\nwindow.G{i} = {{ run{i} }};\n" for i in range(n)}
    files["use.js"] = _each("G{i}.run{i}();", n)
    return files


def _same_name(n: int) -> Files:
    files = {f"p{i}.js": f"window.Lib = {{ a{i}: function () {{}} }};\n" for i in range(n)}
    files["use.js"] = _each("Lib.a{i}();", n)
    return files


def _uses(n: int) -> Files:
    files = {"pub.js": "function run() {}\nwindow.Lib = { run };\n"}
    files.update(
        {f"u{i}.js": "Lib.run();\nLib.run();\nLib.missing();\ndocument.title;\n" for i in range(n)}
    )
    return files


def _declared(n: int) -> Files:
    files = {f"d{i}.d.ts": f"declare const D{i}: number;\n" for i in range(n)}
    files["use.js"] = _each("D{i}.toFixed();", n)
    return files


def _namespaces(n: int) -> Files:
    template = "var NS{i};\n(function (NS{i}) {{ NS{i}.a = 1; }})(NS{i} || (NS{i} = {{}}));\n"
    files = {f"n{i}.js": template.format(i=i) for i in range(n)}
    files["use.js"] = _each("NS{i}.a;\nNS{i}.b();", n)
    return files


def _aliases(n: int) -> Files:
    return {
        "pub.js": "function run() {}\nwindow.Lib = { run };\n",
        "use.js": _each("const A{i} = window.Lib;\nA{i}.run();", n),
    }


def _unknown(n: int) -> Files:
    return {"use.js": _each("U{i}.go();\nU{i}.a.b;", n)}


def _opaque_writes(n: int) -> Files:
    files = {f"w{i}.js": f"window[name{i}] = 1;\neval('x{i}');\n" for i in range(n)}
    files["pub.js"] = "function run() {}\nwindow.Lib = { run };\n"
    files["use.js"] = _each("Lib.run();", n)
    return files


def _factories(n: int) -> Files:
    files = {
        f"f{i}.js": f"function make{i}() {{ return {{ go{i} }}; }}\nfunction go{i}() {{}}\n"
        f"window.F{i} = {{ make{i} }};\n"
        for i in range(n)
    }
    files["use.js"] = _each("const o{i} = F{i}.make{i}();\no{i}.go{i}();", n)
    return files


# The project of each shape, and the count that the debug build reads in about 0.1 s.
SHAPES: dict[str, tuple[Callable[[int], Files], int]] = {
    "publishers": (_publishers, 60),
    "same-name": (_same_name, 60),
    "uses": (_uses, 60),
    "declared": (_declared, 60),
    "namespaces": (_namespaces, 60),
    "aliases": (_aliases, 80),
    "unknown": (_unknown, 100),
    "opaque-writes": (_opaque_writes, 60),
    "factories": (_factories, 40),
}


def _write(root: Path, files: Files) -> Path:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tsconfig.json").write_text(CONFIG, encoding="utf-8")
    for name, text in files.items():
        (root / "src" / name).write_text(text, encoding="utf-8")
    return root


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_the_dependencies_equal_the_python_collector_at_small_sizes(
    native_binary: Path, tmp_path: Path, name: str
) -> None:
    make, _ = SHAPES[name]
    for count in (1, 3, 25):
        root = _write(tmp_path / f"n{count}", make(count))
        found = _differences(native_binary, _request(root, "app", "tsconfig.json"))
        assert found == [], (name, count)


def _run(binary: Path, root: Path) -> Taken:
    wall, cpu, done = timed_run([str(binary)], wire_request(root))
    assert done.returncode == 0, done.stderr[-300:]
    return Taken(cpu=cpu, wall=wall)


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_the_time_grows_linearly_with_the_size_of_the_project(
    tmp_path: Path,
    collector: Path,  # noqa: F811
    name: str,
) -> None:
    timing = timing_for_profile()
    make, base = SHAPES[name]
    n = max(1, base // 10)
    roots: dict[int, Path] = {}

    def project(size: int) -> Path:
        if size not in roots:
            roots[size] = _write(tmp_path / f"n{size}", make(size))
        return roots[size]

    first = _run(collector, project(n))
    for _ in range(6):
        if first.cpu >= timing.measurable:
            break
        n *= 2
        first = _run(collector, project(n))
    small, large = interleaved_least(
        lambda size: _run(collector, project(size)), n, 2 * n, seed=first
    )
    ratio = large.cpu / small.cpu
    print(f"DEPS {name} n={n} t(n)={small.cpu:.3f} t(2n)={large.cpu:.3f} ratio={ratio:.2f}")
    assert small.cpu >= timing.min_time, f"{name}: {small.cpu:.3f} s CPU is too short to measure"
    assert large.cpu < CAP, f"{name}: {large.cpu:.1f} s CPU for n={2 * n}"
    assert ratio < SCRIPT_RATIO, (
        f"{name}: n={n} {small.cpu:.3f} s, 2n {large.cpu:.3f} s, ratio {ratio:.2f}"
    )
