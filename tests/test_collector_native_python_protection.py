# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare provider headers and member protection before convergence (AD-410)."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest
from filelock import FileLock
from python_protection_costs import COSTS
from python_protection_probes import PROBES
from test_collector_native_python_parse import _minor
from test_collector_native_python_proofs import _compare as _proof_compare
from test_collector_native_python_proofs import _rows, _same, _stricter_pin
from test_collector_native_python_scope import _FIXTURES

from archkeel.analyzer.python import source as s
from archkeel.analyzer.python.imports import collect_imports


@pytest.fixture(scope="session")
def python_dump_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the protection dump")
    if cargo is None:
        pytest.skip("the protection dump needs cargo")
    native = Path(__file__).parents[1] / "native"
    target = native / "target" / "dump"
    target.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if os.name == "nt" else ""
    name = "archkeel-python-collector" + suffix
    copy = tmp_path_factory.mktemp("protection-binary") / name
    with FileLock(str(native / "target" / ".pytest-native-build.lock")):
        built = subprocess.run(
            [
                cargo,
                "build",
                "--locked",
                "-p",
                "archkeel-python-collector",
                "--features",
                "dump",
                "--target-dir",
                str(target),
            ],
            cwd=native,
            capture_output=True,
            text=True,
            check=False,
        )
        assert built.returncode == 0, built.stderr
        shutil.copy2(target / "debug" / name, copy)
    return copy


def _python(root: Path, rel: str) -> dict[str, Any] | None:
    namespace = Path(rel).parts[0].removesuffix(".py")
    parsed = s.parse_sources([root / rel], root=root, namespace=namespace)
    if not parsed.modules:
        return None
    m = parsed.modules[0]
    collect_imports([m], {m.module}, {}, namespace=namespace)

    def sites(nodes: Any) -> list[list[int]]:
        return sorted([*s.location(n)] for n in nodes)

    def pairs(values: Any) -> list[list[str]]:
        return sorted([*p] for p in values)

    unsafe = frozenset({m.module})
    classes = []
    for n in m.all_nodes:
        if isinstance(n, ast.ClassDef):
            classes.append(
                [
                    n.lineno,
                    {
                        "typed_header": s.typed_dict_header_static(m, n, unsafe),
                        "base_operands": s._class_base_operands_static(m, n),
                        "creation": [
                            s.class_creation_static(
                                m, n, owner_exposure_only=b, unsafe_providers=unsafe
                            )
                            for b in (False, True)
                        ],
                        "dataclass": s.native_dataclass_header_static(m, n, unsafe),
                        "native": s.native_owner_creation_static(m, n, unsafe),
                        "generic": [
                            s._native_generic_base_static(m, base, n, unsafe) for base in n.bases
                        ],
                    },
                ]
            )
    modes = []
    for owner in (False, True):
        contained, namespace_owners = s._contained_member_roots(
            m, m.all_nodes, owner_exposure_only=owner, unsafe_providers=unsafe
        )
        modes.append(
            {
                "contained": pairs(contained),
                "namespace_owners": sorted(namespace_owners),
                "unproven": sorted(
                    s.unproven_member_bindings(
                        m, owner_exposure_only=owner, unsafe_providers=unsafe
                    )
                ),
                "protected": sites(
                    s._protected_member_references(
                        m,
                        m.all_nodes,
                        member_surface=True,
                        owner_exposure_only=owner,
                        unsafe_providers=unsafe,
                    )
                ),
                "escapes": sites(
                    s.member_escape_references(
                        m,
                        m.all_nodes,
                        member_surface=True,
                        owner_exposure_only=owner,
                        unsafe_providers=unsafe,
                    )
                ),
            }
        )
    constructors = s.proven_constructor_return_candidates(m)
    try:
        quoted = [
            [index, s.annotation_text(s.quoted_type_expression(n))]
            for index, n in enumerate(m.all_nodes)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
    except UnicodeError:
        return None
    return {
        "overloads": sorted(s.static_overload_bindings(m)),
        "explicit": sorted(s.explicit_provider_escapes(m)),
        "classes": classes,
        "owners": [[name, *s.location(node)] for name, node in m._contained_owners],
        "static_containment": pairs(m._static_containment),
        "modes": modes,
        "types": sites(s._type_reference_nodes(m, s._protected_type_expressions(m.all_nodes))),
        "class_values": sites(s._class_value_expressions(m)),
        "constructors": sorted([[*s.location(n)], pairs(deps)] for n, deps in constructors.items()),
        "typed_providers": sorted(
            name for name in m.bound_names if s.native_typed_dict_provider_static(m, name, unsafe)
        ),
        "quoted": quoted,
    }


def _native(binary: Path, root: Path, paths: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(
        [str(binary), "--dump-protection", str(_minor()), str(root)],
        input="".join(f"{p}\n" for p in paths),
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_protection_dump_exists(tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(
        "from typing import TypedDict\nclass C(TypedDict):\n x: int\n"
    )
    rows = _native(python_dump_binary, tmp_path, ["probe.py"])
    assert len(rows) == 1, rows
    assert rows[0]["full_scope"], rows
    _same(rows[0]["data"], _python(tmp_path, "probe.py"), "provider protection")


@pytest.mark.parametrize("index", range(len(PROBES)))
def test_generated_protection(index: int, tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(PROBES[index])
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert row["full_scope"], row
    assert row["work"] == COSTS[index]
    _same(row["data"], _python(tmp_path, "probe.py"), index)
    if report := os.environ.get("ARCHKEEL_PROTECTION_COST_REPORT"):
        with Path(report).open("a") as stream:
            stream.write(json.dumps([_minor(), index, row["work"]]) + "\n")


def _compare(binary: Path, root: Path, private: bool = False) -> tuple[int, int, int, int]:
    paths = sorted(
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if p.is_file() and not p.is_symlink() and ".venv" not in p.parts
    )
    assert paths, "protection corpus has no Python files"
    equal, stricter, maximum = 0, {}, 0
    for row in _rows(binary, root, paths, "--dump-protection"):
        expected = _python(root, row["file"])
        maximum = max(maximum, row["work"])
        if private:
            if (expected is None) != (not row["full_scope"]):
                raise AssertionError("private corpus has an unexpected refusal")
            if expected is not None and json.dumps(
                row["data"], sort_keys=True, ensure_ascii=False
            ) != json.dumps(expected, sort_keys=True, ensure_ascii=False):
                raise AssertionError("private corpus data differs")
            equal += 1
        elif expected is None:
            assert not row["full_scope"], row["file"]
            equal += 1
        elif not row["full_scope"]:
            stricter[row["file"]] = row["gap"]
        else:
            _same(row["data"], expected, row["file"])
            equal += 1
        if (report := os.environ.get("ARCHKEEL_PROTECTION_WORK_REPORT")) and not private:
            with Path(report).open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "minor": _minor(),
                            "root": root.name,
                            "file": row["file"],
                            "work": row["work"],
                        }
                    )
                    + "\n"
                )
    assert equal + len(stricter) == len(paths)
    assert stricter == ({} if private else _stricter_pin(root))
    return len(paths), equal, len(stricter), maximum


@pytest.mark.parametrize("fixture", (*_FIXTURES, "fixtures"))
def test_fixture_protection(fixture: str, python_dump_binary: Path) -> None:
    print(
        "protection fixtures",
        _minor(),
        fixture,
        _compare(python_dump_binary, Path(__file__).parents[1] / fixture),
    )


@pytest.mark.skipif(
    not os.environ.get("ARCHKEEL_PROTECTION_PUBLIC_CORPORA"), reason="no corpus is named"
)
def test_corpus_protection(python_dump_binary: Path) -> None:
    for index, root in enumerate(
        os.environ["ARCHKEEL_PROTECTION_PUBLIC_CORPORA"].split(os.pathsep)
    ):
        print(
            "protection public parity",
            _minor(),
            index,
            _compare(python_dump_binary, Path(root)),
            flush=True,
        )


@pytest.mark.skipif(
    not os.environ.get("ARCHKEEL_PROTECTION_PRIVATE_CORPORA"), reason="no private corpus is named"
)
def test_private_corpus_protection(python_dump_binary: Path) -> None:
    total = equal = maximum = 0
    for root in os.environ["ARCHKEEL_PROTECTION_PRIVATE_CORPORA"].split(os.pathsep):
        counts = _compare(python_dump_binary, Path(root), private=True)
        total += counts[0]
        equal += counts[1]
        maximum = max(maximum, counts[3])
    print("protection private aggregate", _minor(), total, equal, maximum, flush=True)


def test_empty_protection_corpus(tmp_path: Path, python_dump_binary: Path) -> None:
    with pytest.raises(AssertionError, match="protection corpus has no Python files"):
        _compare(python_dump_binary, tmp_path)


@pytest.mark.parametrize("compare", (_compare, _proof_compare))
def test_stricter_file_pins_reject_additions_and_removals(
    compare: Any, tmp_path: Path, python_dump_binary: Path
) -> None:
    root = tmp_path / "pydantic"
    known = root / "pydantic-core/wasm-preview/run_tests.py"
    known.parent.mkdir(parents=True)
    known.write_text("await f()\n")
    assert compare(python_dump_binary, root) == (1, 0, 1, 0)
    known.write_text("pass\n")
    with pytest.raises(AssertionError):
        compare(python_dump_binary, root)
    known.write_text("await f()\n")
    (root / "extra.py").write_text("await f()\n")
    with pytest.raises(AssertionError):
        compare(python_dump_binary, root)


@pytest.mark.requires_python(12)
@pytest.mark.parametrize(
    "text",
    (
        "class C: pass\ntype A = list[C]\n",
        "type A[T] = tuple[T, T]\n",
        "class C[T]:\n x: T\n",
        "def f[T](x: T) -> T: return x\n",
    ),
)
def test_modern_protection(text: str, tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(text)
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert row["full_scope"], row
    _same(row["data"], _python(tmp_path, "probe.py"), "PEP 695")


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
def test_hostile_protection(raw: bytes, tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_bytes(raw)
    start = perf_counter()
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    elapsed = perf_counter() - start
    assert elapsed < 20
    if not row["full_scope"]:
        assert row["gap"] and "data" not in row
    print("protection hostile", len(raw), elapsed, row.get("gap"))


def test_protection_work_scales(tmp_path: Path, python_dump_binary: Path) -> None:
    works = []
    for size in (1000, 3000):
        (tmp_path / "probe.py").write_text(
            "".join(f"class C{i}:\n @staticmethod\n def f(): pass\n" for i in range(size))
        )
        row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
        assert row["full_scope"], row.get("gap")
        works.append(row["work"])
    print("protection work scaling", _minor(), works)
    assert works == [1279907, 3841907]
    assert 2.8 < works[1] / works[0] < 3.2


def test_quoted_surrogate_refuses_the_complete_table(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    (tmp_path / "probe.py").write_text("x = '\\ud800'\n")
    assert _python(tmp_path, "probe.py") is None
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert not row["full_scope"] and "data" not in row
    assert row["gap"] == "quoted expression surrogate value unseen"


@pytest.mark.parametrize(
    "rel,text",
    (
        ("typing.py", "from typing import TypedDict, Generic\nclass C(TypedDict):\n x: int\n"),
        ("dataclasses.py", "from dataclasses import dataclass\n@dataclass\nclass C: pass\n"),
        (
            "typing_extensions.py",
            "from typing_extensions import TypedDict\nclass C(TypedDict): pass\n",
        ),
    ),
)
def test_a_scanned_factory_provider_is_unsafe(
    rel: str, text: str, tmp_path: Path, python_dump_binary: Path
) -> None:
    (tmp_path / rel).write_text(text)
    row = _native(python_dump_binary, tmp_path, [rel])[0]
    assert row["full_scope"], row
    _same(row["data"], _python(tmp_path, rel), rel)
    assert row["data"]["classes"][0][1]["native"] is False


def test_quoted_depth_refusal_is_pinned(tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text("x = " + repr(" | ".join(["A"] * 150)) + "\n")
    assert _python(tmp_path, "probe.py") is not None
    row = _native(python_dump_binary, tmp_path, ["probe.py"])[0]
    assert not row["full_scope"] and "data" not in row
    assert row["gap"] == "binding expression text unseen: Deep"
