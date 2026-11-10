# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The standard-global catalog follows the compiler's own lib files for each `lib` and target."""

import hashlib
import json
import pickle
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest
from test_typescript_standard_globals import _environment

from archkeel.analyzer.typescript import standard_libs
from archkeel.analyzer.typescript.config import (
    ModuleKind,
    Options,
    ScriptTarget,
    standard_globals,
)
from archkeel.analyzer.typescript.standard_libs import (
    DEFAULT_LIBS,
    LIB_GLOBALS,
    LIB_REFERENCES,
    TYPESCRIPT_VERSION,
    StandardLibrary,
)

ROOT = Path(__file__).resolve().parents[1]
TYPESCRIPT_LIB = ROOT / "tools/browser-runtime/node_modules/typescript/lib"


@pytest.mark.parametrize(
    ("compiler", "present", "missing"),
    [
        (
            {"lib": ["ES2020", "DOM", "DOM.Iterable"]},
            {"Math", "Date", "Map", "BigInt", "document", "console"},
            {"WeakRef"},
        ),
        ({"lib": ["es5"]}, {"Math", "Date"}, {"document", "Map"}),
        ({"lib": ["es2015"]}, {"Map", "Promise", "Math"}, {"document", "WeakRef"}),
        ({"lib": ["es6"]}, {"Map", "Promise"}, {"document"}),
        ({"lib": ["es2020"]}, {"BigInt", "Map"}, {"WeakRef", "document"}),
        ({"target": "es2022"}, {"Map", "document", "WeakMap"}, set()),
        ({"target": "es2015"}, {"Map", "Promise", "document"}, {"WeakRef"}),
        ({"target": "esnext"}, {"WeakRef", "document", "Iterator"}, set()),
        ({"module": "node16"}, {"Map", "document"}, set()),
        ({"module": "commonjs"}, {"String", "document"}, {"Map"}),
        ({}, {"String", "Math", "document"}, {"Map", "Promise"}),
    ],
)
def test_lib_and_default_target_prove_exactly_the_compiler_globals(
    tmp_path, compiler, present, missing
):
    config, snapshot = _environment(tmp_path, compiler)
    assert not config.partial and not snapshot.problems and not config.options.lib_unmodeled
    names = standard_globals(config.options)
    assert present <= names
    assert not missing & names


def test_generated_catalog_is_the_one_the_pinned_compiler_produces():
    if not TYPESCRIPT_LIB.is_dir():
        pytest.skip("browser runtime dependencies are not installed")
    result = subprocess.run(
        [sys.executable, "-m", "tools.typescript_libs", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_catalog_records_the_pinned_compiler_version():
    if not TYPESCRIPT_LIB.is_dir():
        pytest.skip("browser runtime dependencies are not installed")
    version = json.loads((TYPESCRIPT_LIB.parent / "package.json").read_text())["version"]
    assert TYPESCRIPT_VERSION == version


def test_catalog_entries_hold_the_declared_globals_of_their_library():
    assert LIB_GLOBALS[StandardLibrary("es5")] and "Math" in LIB_GLOBALS[StandardLibrary("es5")]
    assert "console" in LIB_GLOBALS[StandardLibrary("dom")]
    assert "WeakRef" in LIB_GLOBALS[StandardLibrary("es2021.weakref")]


# AD-261: the Python collector and the native collector read this one data file. Every digest below
# was printed from the generated Python module before it became JSON, so a change in what a lookup
# returns shows as a different digest, not as a silent drift of the data file.
CATALOG_DIGEST = "b2b16641f75c995f0efa160c1cc391922f72f7a3bd3cb30173f74d43ee31ec67"
LOOKUP_DIGEST = "a1f1f155d4e8a670f423db8b5efb366390c7d68e089778f8c143013c118322d7"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def test_catalog_data_is_the_data_the_generated_module_held():
    libs = {
        str(library): (
            sorted(LIB_GLOBALS[library]),
            [str(reference) for reference in LIB_REFERENCES[library]],
        )
        for library in sorted(LIB_GLOBALS)
    }
    defaults = {key: [str(item) for item in refs] for key, refs in DEFAULT_LIBS.items()}
    data = {"version": TYPESCRIPT_VERSION, "libs": libs, "defaults": defaults}
    assert len(libs) == 97
    assert _digest(data) == CATALOG_DIGEST


def test_lookups_return_the_same_globals_for_every_lib_and_target():
    lookups = {}
    for library in sorted(LIB_GLOBALS):
        lookups[f"lib:{library}"] = sorted(standard_globals(Options(libs=(library,))))
    for target in ScriptTarget:
        lookups[f"target:{target.value}"] = sorted(standard_globals(Options(target=target)))
        for module in ModuleKind:
            key = f"target:{target.value}:{module.value}"
            lookups[key] = sorted(standard_globals(Options(target=target, module=module)))
    for module in ModuleKind:
        lookups[f"module:{module.value}"] = sorted(standard_globals(Options(module=module)))
    lookups["none"] = sorted(standard_globals(Options()))
    assert len(lookups) == 337
    assert _digest(lookups) == LOOKUP_DIGEST


def test_default_libs_name_every_script_target_and_only_those():
    assert set(DEFAULT_LIBS) == {target.value for target in ScriptTarget}


def test_standard_library_is_a_closed_nominal_name():
    es5 = StandardLibrary("es5")
    assert es5 == "es5" and str(es5) == "es5" and isinstance(es5, StandardLibrary)
    assert StandardLibrary("es5") is es5
    assert not isinstance("es5", StandardLibrary)
    assert {str(library) for library in LIB_GLOBALS} == set(json.loads(_catalog_text())["libs"])
    with pytest.raises(ValueError, match="nonsense"):
        StandardLibrary("nonsense")
    with pytest.raises(ValueError):
        StandardLibrary("ES5")


def _catalog_text() -> str:
    return files("archkeel.analyzer.typescript").joinpath("standard_libs.json").read_text("utf-8")


def test_the_native_collector_embeds_a_copy_of_the_catalog_that_equals_it():
    # The copy lies in `native/`, so the digest of the workspace covers it (AD-352).
    native = ROOT / "native/typescript/standard_libs.json"
    assert native.read_bytes() == _catalog_text().encode("utf-8")


def test_catalog_file_is_compact_sorted_and_ends_in_one_newline():
    text = _catalog_text()
    data = json.loads(text)
    assert text == json.dumps(data, separators=(",", ":")) + "\n"
    assert list(data) == ["typescript_version", "libs", "defaults"]
    assert list(data["libs"]) == sorted(data["libs"])
    assert all(list(lib) == ["globals", "references"] for lib in data["libs"].values())
    assert all(lib["globals"] == sorted(lib["globals"]) for lib in data["libs"].values())
    assert list(data["defaults"]) == sorted(data["defaults"])


def test_python_module_holds_no_second_copy_of_the_data():
    module = ROOT / "src/archkeel/analyzer/typescript/standard_libs.py"
    assert len(module.read_text(encoding="utf-8").splitlines()) < 100


def test_every_pickle_protocol_returns_the_registered_name():
    es5 = StandardLibrary("es5")
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        assert pickle.loads(pickle.dumps(es5, protocol)) is es5


def _broken_copy(tmp_path, change):
    data = json.loads(standard_libs._DATA.read_bytes())
    change(data)
    path = tmp_path / "standard_libs.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_loader_reads_a_valid_copy_without_touching_the_module_state(tmp_path):
    known_before = dict(standard_libs._KNOWN)
    path = _broken_copy(tmp_path, lambda data: None)
    version, libs, references, defaults, known = standard_libs._load(path)
    assert version == TYPESCRIPT_VERSION and set(libs) == set(LIB_GLOBALS)
    assert set(references) == set(libs) and set(defaults) == set(DEFAULT_LIBS)
    assert set(known) == {str(name) for name in libs}
    assert standard_libs._KNOWN == known_before


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data.update(libs={}),
        lambda data: data.pop("defaults"),
        lambda data: data.pop("libs"),
        lambda data: data.pop("typescript_version"),
        lambda data: data["libs"]["es5"]["references"].append("nonsense"),
        lambda data: data.update(libs=[]),
    ],
    ids=["empty-libs", "no-defaults", "no-libs", "no-version", "unknown-reference", "wrong-shape"],
)
def test_loader_fails_closed_on_a_broken_catalog(tmp_path, change):
    path = _broken_copy(tmp_path, change)
    with pytest.raises(standard_libs.CatalogError, match="broken install") as raised:
        standard_libs._load(path)
    assert str(path) in str(raised.value)


def test_loader_fails_closed_on_a_missing_file(tmp_path):
    path = tmp_path / "standard_libs.json"
    with pytest.raises(standard_libs.CatalogError, match="broken install") as raised:
        standard_libs._load(path)
    assert str(path) in str(raised.value)


@pytest.mark.parametrize("content", [b"{not json", b"\xff\xfe", b""])
def test_loader_fails_closed_on_corrupt_json(tmp_path, content):
    path = tmp_path / "standard_libs.json"
    path.write_bytes(content)
    with pytest.raises(standard_libs.CatalogError, match="broken install") as raised:
        standard_libs._load(path)
    assert str(path) in str(raised.value)


def test_catalog_error_is_a_value_error():
    assert issubclass(standard_libs.CatalogError, ValueError)


def _generator():
    if not TYPESCRIPT_LIB.is_dir():
        pytest.skip("browser runtime dependencies are not installed")
    from tools import typescript_libs

    return typescript_libs


def test_generator_output_has_no_carriage_return():
    assert b"\r" not in _generator().build_catalog().encode("utf-8")
    assert b"\r" not in (ROOT / "src/archkeel/analyzer/typescript/standard_libs.json").read_bytes()


def test_check_compares_bytes_and_write_emits_lf(tmp_path, monkeypatch):
    generator = _generator()
    target = tmp_path / "standard_libs.json"
    monkeypatch.setattr(generator, "ROOT", tmp_path)
    copy = tmp_path / "native.json"
    monkeypatch.setattr(generator, "OUTPUT", target)
    monkeypatch.setattr(generator, "NATIVE", copy)
    expected = generator.build_catalog().encode("utf-8")
    assert generator.main(["--write"]) == 0
    assert target.read_bytes() == copy.read_bytes() == expected
    assert generator.main(["--check"]) == 0
    # The same text with Windows line endings is a different file: Rust embeds the bytes.
    target.write_bytes(expected.replace(b"\n", b"\r\n"))
    assert generator.main(["--check"]) == 1
    target.write_bytes(expected)
    copy.write_bytes(b"{}\n")
    assert generator.main(["--check"]) == 1


def test_gitattributes_pins_the_data_file_to_lf():
    result = subprocess.run(
        [
            "git",
            "check-attr",
            "text",
            "eol",
            "--",
            "src/archkeel/analyzer/typescript/standard_libs.json",
            "native/typescript/standard_libs.json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.count("text: set") == result.stdout.count("eol: lf") == 2
