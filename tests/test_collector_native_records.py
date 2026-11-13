# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340 (PR 4.3a-3a): the records pass of the native TypeScript collector is linear.

Consumer: the native TypeScript collector. The `dump` feature prints the records of the expanded
imports and the constructs (`--dump-records`). Each shape is measured at two sizes: the time and
the peak memory must not grow faster than the size.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from collector_wire import request_bytes
from conftest import build_native_copy
from test_collector_native_imports import (
    CONFIGS,
    _write,
)


@pytest.fixture(scope="session")
def records_binary(
    native_binary: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:  # pragma: no cover - build
    assert native_binary.is_file()
    return build_native_copy(tmp_path_factory, "native-dump", ("dump",))


# The records pass must be linear in time and in memory. Python scans the bindings of the file for
# each statement and the exports of a module for each bound name, which is quadratic in a file with
# n statements or n exports. Each shape holds a different loop: many statements that each bind one
# name, one statement with many names, many importing files, and comparisons in one chain. The
# CPU time of the dump (the debug build) at 2n over n must stay below 3 (linear is about 2), and its
# peak memory below 2.5 times.
RATIO = 3.0
GROWTH = 2.5


def _records_shape(name: str, n: int) -> dict[str, str]:
    exports = "".join(f"export const x{i} = {i};\n" for i in range(n))
    files = {"tsconfig.json": CONFIGS["node10"], "src/a.ts": exports}
    match name:
        case "many-statements":
            files["src/b.ts"] = "".join(f"import {{ x{i} }} from './a';\n" for i in range(n))
        case "one-statement":
            names = ", ".join(f"x{i} as y{i}" for i in range(n))
            files["src/b.ts"] = f"import {{ {names} }} from './a';\n"
        case "many-importers":
            for i in range(n):
                files[f"src/f{i}.ts"] = f"import {{ x{i} }} from './a';\n"
        case "comparisons":
            files["src/b.ts"] = (
                "const r = " + " || ".join(f"k === 'v{i}'" for i in range(n)) + ";\n"
            )
            files["src/c.ts"] = "".join(
                f"function f{i}(k) {{ return k == 'w{i}'; }}\n" for i in range(n)
            )
        case "sites-resolution":
            # Many calls, references and `new` expressions of names that the module defines, that
            # it imports and that the enclosing class declares: each site asks the resolver.
            files["src/b.ts"] = (
                "".join(f"import {{ x{i} }} from './a';\nconst v{i} = x{i};\n" for i in range(n))
                + "".join(f"export function g{i}() {{ return g{i}(); }}\n" for i in range(n))
                + "".join(
                    f"class C{i} {{ f = {i}; m() {{ return this.f + new C{i}().f; }} }}\n"
                    for i in range(n)
                )
                + "".join(f"const o{i} = new C{i}(g{i}, x{i});\n" for i in range(n))
            )
        case "sites-shadow-nest":
            # n nested arrow functions that each declare a name, and n sites at the bottom that ask
            # whether a scope of their chain hides their name: a union of the sets is n squared.
            files["src/b.ts"] = (
                "const f = "
                + "".join(f"(p{i}) => {{ var v{i}; return " for i in range(n))
                + "["
                + ", ".join(f"v{i}(p{i})" for i in range(n))
                + "]"
                + "; }" * n
                + ";\n"
            )
        case "symbols-bases":
            files["src/b.ts"] = "".join(
                f"interface I{i} {{ a{i}: number }}\n@d({i}) class C{i} extends C{max(i - 1, 0)} "
                f"implements I{i} {{ m(): void {{}} }}\n"
                for i in range(n)
            )
        case "symbols-members":
            # One class with n fields and n methods, n overloads of a function and of a method, one
            # enum with n members and n small enums: the loops over members and over the
            # definitions that share a name.
            body = "".join(
                f"  f{i}: number = {i};\n  m{i}(a: number): void {{}}\n  m(a: number): void;\n"
                for i in range(n)
            )
            files["src/b.ts"] = (
                f"class K {{\n{body}  m(a: any) {{}}\n}}\n"
                + "".join("function f(a: number): void;\n" for _ in range(n))
                + "function f(a: any) {}\n"
                + "enum Big { "
                + ", ".join(f"A{i}" for i in range(n))
                + " }\n"
                + "".join(f"enum E{i} {{ X, Y = {i}, Z }}\n" for i in range(n))
            )
        case _:
            raise AssertionError(name)
    return files


def _run(binary: Path, payload: bytes) -> tuple[float, float]:
    """One run of the dump: its CPU seconds and its peak memory in MiB, from the same `wait4`."""
    process = subprocess.Popen(
        [str(binary), "--dump-records"], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(payload)
    process.stdin.close()
    process.stdout.read()
    _, status, usage = os.wait4(process.pid, 0)
    assert status == 0
    peak = usage.ru_maxrss / (2**20 if os.uname().sysname == "Darwin" else 2**10)
    return usage.ru_utime + usage.ru_stime, peak


def _measure(binary: Path, root: Path, name: str, n: int) -> tuple[float, float]:
    """The least CPU seconds of two runs, and the largest peak memory in MiB."""
    shutil.rmtree(root, ignore_errors=True)
    _write(root, _records_shape(name, n))
    runs = [_run(binary, request_bytes(root, "app", "tsconfig.json")) for _ in range(2)]
    return min(cpu for cpu, _ in runs), max(peak for _, peak in runs)


RECORD_SHAPES = (
    ("many-statements", 700),
    ("one-statement", 1500),
    ("many-importers", 700),
    ("comparisons", 1000),
    ("sites-resolution", 500),
    ("sites-shadow-nest", 800),
    ("symbols-members", 500),
    ("symbols-bases", 700),
)


@pytest.mark.parametrize(("name", "n"), RECORD_SHAPES)
def test_the_records_pass_is_linear_in_time_and_memory(
    tmp_path: Path, records_binary: Path, name: str, n: int
) -> None:
    first_cpu, first_peak = _measure(records_binary, tmp_path / "one", name, n)
    second_cpu, second_peak = _measure(records_binary, tmp_path / "two", name, 2 * n)
    print(
        f"RECORDS {name} n={n} cpu {first_cpu:.3f} s 2n {second_cpu:.3f} s ratio "
        f"{second_cpu / first_cpu:.2f}; peak {first_peak:.0f} MiB 2n {second_peak:.0f} MiB"
    )
    assert first_cpu > 0.05, f"{name}: n={n} is too small to measure"
    assert second_cpu / first_cpu < RATIO
    assert second_peak <= GROWTH * first_peak
