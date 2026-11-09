# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-323 (PR 4.3a-3a): the native records of the expanded imports and the constructs equal Python.

Consumer: PR 4.3a-3d, which puts the records on the wire. The reply of the native collector does
not carry them yet, and its capability stays legacy, so the host never reads them. The `dump`
feature prints them (`--dump-records`), and this test compares them with the records of the
unmodified Python collector: the import records with one record for each bound name, their
targets, the `ESM_EXPORT` witnesses, the `TSCONSTRUCT` records and the evidence that they cite.
The Python methods run in the order of `_Collection.facts()` up to `_constructs()`.
"""

from __future__ import annotations

import dataclasses
import json
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import build_native_copy
from test_collector_native_imports import (
    CONFIGS,
    PACKAGES,
    SOURCES,
    SPECIFIERS,
    _imports_of,
    _write,
)
from test_collector_native_syntax import FIXTURES, STUDIO_UI, SYNTAX_PIECES, _mutants, _sources

from archkeel.analyzer.typescript import collect as python_collector
from archkeel.ir.facts import Record
from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import (
    CollectionRequest,
    ProtocolVersion,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

ROOT = Path(__file__).parents[1]
# Folders of further corpora (the x35 tree, a public project): `path:scope:namespace`, separated
# by `;`. Only totals are printed.
CORPORA = "ARCHKEEL_RECORDS_CORPORA"

# Statements that bind names across files: named, default, namespace and type-only imports, a
# re-export, a name that is exported twice, a file with a syntax error, and string comparisons.
EXPORTERS = {
    "src/a.ts": (
        "export const one = 1;\nexport function two() {}\nexport class Three {}\n"
        "export default 4;\nexport type Four = number;\nexport { one as uno };\n"
        "const dup = 1;\nexport { dup };\nexport { dup as dup2 };\n"
        "export function twice() {}\nexport const twice2 = 1;\nexport { twice2 as twice };\n"
    ),
    "src/b.ts": "export * from './a';\nexport { two as deux } from './a';\nexport const b = 1;\n",
    "src/broken.ts": "export const ok = 1;\nexport const = ;\n",
    "src/c.js": "export const cj = 1;\n",
    "src/d.d.ts": "export declare const decl: number;\n",
}
IMPORTERS = {
    "src/i1.ts": (
        "import { one, two as t2, Three } from './a';\nimport def, * as ns from './a';\n"
        "import type { Four } from './a';\nimport { type one as o2, two } from './a';\n"
        "import { deux, b } from './b';\nimport { ok } from './broken';\nimport { cj } "
        "from './c';\n"
        "import { decl } from './d';\nimport { one } from './missing';\nimport { dup, "
        "dup2 } from './a';\n"
        "import { twice } from './a';\nimport { uno } from './a';\n"
        "if (one === 'x' || 'y' != t2 || ns === (`z` as string)) {}\n"
        "function f(kind: string) { switch (kind) { case 'a': return 1; } return kind == 'b'; }\n"
        "class K { m(k) { return k === 'c'; } }\n"
    ),
    "src/i2.ts": "import { one } from './a';\nvar one = 2;\nimport { two } from './a';\ntwo = 3;\n",
    "src/i3.ts": (
        "import { one } from './a'\nimport { one as again } from './a'\nconsole.log(again);\n"
    ),
    "src/i4.ts": (
        "import {\n  one,\n  two,\n} from './a'; const s = 'q'; if (s === 'q') {}\nimport 'x';\n"
    ),
    "src/i5.js": "import { one } from './a';\nwindow.foo = one;\n",
    "src/i6.ts": "import { one } from './a'; export { one }; export default one === 'e';\n",
}


def _request(root: Path, scope: str = "src", namespace: str = "app") -> CollectionRequest:
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope((scope,), namespace),
        TypeScriptSettings("tsconfig.json", False),
        ProtocolVersion.V8,
    )


def _plain_record(record: Record) -> dict[str, object]:
    data = {key: _plain_value(value) for key, value in record.data.entries}
    return {
        "id": record.id,
        "evidence_class": record.evidence_class.value,
        "area": record.area,
        "kind": record.kind,
        "title": record.title,
        "subjects": list(record.subjects),
        "evidence_ids": list(record.evidence_ids),
        "rule_ids": list(record.rule_ids),
        "fact_ids": list(record.fact_ids),
        "provenance": list(record.provenance),
        "data": data,
    }


def _plain_value(value: object) -> object:
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    return value


def _target(target: object) -> dict[str, object]:
    assert dataclasses.is_dataclass(target)
    kind = {
        "LocalTarget": "local",
        "ExternalPackageTarget": "external",
        "BuiltinTarget": "builtin",
        "UnresolvedTarget": "unresolved",
    }[type(target).__name__]
    return {"kind": kind, **dataclasses.asdict(target)}


def python_records(request: CollectionRequest) -> dict[str, object]:
    """The records of the Python collector, built in the order of `_Collection.facts()`."""
    settings = request.resolver
    assert isinstance(settings, TypeScriptSettings)
    collection = python_collector._Collection(request, settings)
    index = 0
    while index < len(collection.queue):
        collection._file(collection.queue[index])
        index += 1
    collection._named_imports()
    constructs = [_plain_record(record) for record in collection._constructs()]
    witnesses = list(collection.import_binding_facts.values())
    imports = sorted(collection.imports, key=lambda item: item["id"])
    cited = {
        evidence
        for record in [*witnesses, *constructs]
        for evidence in record["evidence_ids"]  # type: ignore[attr-defined]
    }
    return {
        "imports": imports,
        "targets": [_target(target) for target in collection.targets],
        "witnesses": witnesses,
        "constructs": constructs,
        "evidence": [collection.evidence[key] for key in sorted(cited)],
    }


@pytest.fixture(scope="session")
def records_binary(
    native_binary: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:  # pragma: no cover - build
    assert native_binary.is_file()
    return build_native_copy(tmp_path_factory, "native-dump", ("dump",))


def native_records(binary: Path, request: CollectionRequest) -> dict[str, object]:
    done = subprocess.run(
        [str(binary), "--dump-records"],
        input=encode_request(request),
        capture_output=True,
        check=False,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")[:2000]
    return json.loads(done.stdout)  # type: ignore[no-any-return]


def _differences(native: dict[str, object], python: dict[str, object]) -> list[str]:
    found: list[str] = []
    for key in python:
        mine, theirs = native[key], python[key]
        if mine == theirs:
            continue
        assert isinstance(mine, list) and isinstance(theirs, list)
        if len(mine) != len(theirs):
            found.append(f"{key}: {len(mine)} native, {len(theirs)} python")
        for one, two in zip(mine, theirs, strict=False):
            if one != two:
                found.append(f"{key}: {str(one)[:300]} native, {str(two)[:300]} python")
                break
    return found


def _compare(binary: Path, request: CollectionRequest) -> dict[str, int]:
    native = native_records(binary, request)
    python = python_records(request)
    assert _differences(native, python) == []
    # Two runs give identical bytes.
    again = subprocess.run(
        [str(binary), "--dump-records"], input=encode_request(request), capture_output=True
    ).stdout
    first = subprocess.run(
        [str(binary), "--dump-records"], input=encode_request(request), capture_output=True
    ).stdout
    assert first == again
    return {key: len(value) for key, value in python.items()}  # type: ignore[arg-type]


@pytest.mark.parametrize("path", [*FIXTURES, STUDIO_UI])
def test_fixture_records_equal_the_python_collector(records_binary: Path, path: str) -> None:
    root = ROOT / path
    if (root / "tsconfig.json").is_file() and path == STUDIO_UI:
        request = _request(root, ".", "ui")
    else:
        from test_collector_native_typescript import _request as fixture_request

        request = fixture_request(root)
    counts = _compare(records_binary, request)
    assert counts["imports"] > 0


def _tree(tmp_path: Path, extra: dict[str, str] | None = None) -> Path:
    files = {"tsconfig.json": CONFIGS["node10"], **EXPORTERS, **IMPORTERS, **PACKAGES, **SOURCES}
    files["src/importer.ts"] = _imports_of(list(SPECIFIERS))
    files.update(extra or {})
    _write(tmp_path, files)
    return tmp_path


def test_named_imports_constructs_and_the_resolution_grid_equal_python(
    tmp_path: Path, records_binary: Path
) -> None:
    counts = _compare(records_binary, _request(_tree(tmp_path)))
    # The comparison is not empty: bound names that are proven, and comparisons.
    assert counts["witnesses"] >= 4
    assert counts["constructs"] >= 8
    assert counts["imports"] > len(SPECIFIERS)


def test_syntax_pieces_in_a_project_equal_python(tmp_path: Path, records_binary: Path) -> None:
    rng = random.Random(4331)
    extra: dict[str, str] = {}
    for index in range(60):
        body = "\n".join(rng.choice(SYNTAX_PIECES) for _ in range(rng.randint(2, 8)))
        suffix = rng.choice([".ts", ".tsx", ".mts"])
        extra[f"src/piece{index}{suffix}"] = (
            "import { one, two as t } from './a';\n" + body + "\nif (t === 'p') {}\n"
        )
    counts = _compare(records_binary, _request(_tree(tmp_path, extra)))
    assert counts["constructs"] > 40


def test_mutated_projects_equal_python(tmp_path: Path, records_binary: Path) -> None:
    source = _tree(tmp_path / "seed")
    seeds = _sources(source, "src")
    for round_index in range(3):
        project = tmp_path / f"m{round_index}"
        shutil.copytree(source, project)
        mutated = _mutants([(rel, project / rel) for rel, _ in seeds], 25 + round_index)
        for rel, data in mutated:
            target = project / rel.split("/", 1)[1]
            if target.suffix in (".ts", ".js"):
                target.write_bytes(data)
        _compare(records_binary, _request(project))


def test_private_corpora_equal_python(records_binary: Path) -> None:
    value = os.environ.get(CORPORA)
    if not value:
        pytest.skip(f"{CORPORA} names no corpus")
    for entry in value.split(";"):
        path, scope, namespace = entry.split(":")
        counts = _compare(records_binary, _request(Path(path), scope, namespace))
        # Totals only: a private corpus must not leak a name into a report.
        print("corpus:", ", ".join(f"{key} {count}" for key, count in sorted(counts.items())))


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
        case _:
            raise AssertionError(name)
    return files


def _measure(binary: Path, root: Path, name: str, n: int) -> tuple[float, float]:
    """The least CPU seconds of three runs, and the peak memory in MiB."""
    from collector_timing import timed_run

    shutil.rmtree(root, ignore_errors=True)
    _write(root, _records_shape(name, n))
    payload = encode_request(_request(root))
    cpu = min(timed_run([str(binary), "--dump-records"], payload)[1] for _ in range(3))
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
    return cpu, peak


RECORD_SHAPES = (
    ("many-statements", 1500),
    ("one-statement", 4000),
    ("many-importers", 1500),
    ("comparisons", 2500),
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
