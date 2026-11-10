# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340 (PR 4.3a-5): the script dependencies of the native collector equal the Python collector.

Consumer: `native/typescript/src/script_*.rs`, through the process port. The oracle is
`collect.collect`, unmodified: every section, the targets, the gaps and the evidence of a project
whose files are global scripts that publish, alias, destructure, declare and use globals.

Each project of the grid has one branch of `_script_dependencies`: a publication that is stable or
not, a factory, a namespace, a `declare`, a standard global, a vendored library, a write that no
publication bounds. Mutated copies reach the branches that a person would not write.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

import pytest
from test_collector_native_imports import _differences, _request
from test_collector_native_script_syntax import _mutate

CONFIG = '{"compilerOptions":{"allowJs":true,"target":"es2020"},"include":["src"]}'
PUBLISHER = "function run() {}\nfunction stop() {}\nwindow.Lib = { run, stop };\n"

# One project of the grid: the files under `src`, and the TSConfig when it is not the default.
GRID: dict[str, dict[str, str]] = {
    "published-member": {"pub.js": PUBLISHER, "use.js": "Lib.run();\nLib.stop();\n"},
    "published-read": {"pub.js": PUBLISHER, "use.js": "var f = Lib.run;\nf();\nLib;\n"},
    "unknown-member": {"pub.js": PUBLISHER, "use.js": "Lib.missing();\nLib.run.call(null);\n"},
    "unpublished": {"use.js": "Missing.go();\nMissing.a.b();\n"},
    "published-twice": {
        "a.js": PUBLISHER,
        "b.js": "window.Lib = { run: function () {} };\n",
        "use.js": "Lib.run();\n",
    },
    "published-and-written": {"pub.js": PUBLISHER, "use.js": "Lib.run();\nLib = {};\nLib.x = 1;\n"},
    "wrapper-publication": {
        "pub.js": "(function (g) { function a() {} g.Wrap = { a }; })(window);\n",
        "use.js": "Wrap.a();\n",
    },
    "return-publication": {
        "pub.js": "var Scene = (function () { function create() {} return { create }; })();\n",
        "use.js": "Scene.create();\nScene.other();\n",
    },
    "standard-globals": {
        "use.js": "document.title;\nArray.from([]);\nPromise.resolve(1);\nundefined;\nnew Map();\n",
    },
    "standard-with-error": {
        "bad.js": "function (\n",
        "use.js": "document.title;\nArray.from([]);\n",
    },
    "shadowed-standard": {
        "use.js": "function f(document) { document.title; }\nvar Array = {};\nArray.from();\n",
    },
    "declared-global": {
        "decl.d.ts": "declare const Legacy: { go(): void };\n",
        "use.js": "Legacy.go();\n",
    },
    "declared-and-bound": {
        "decl.d.ts": "declare const Both: number;\n",
        "other.js": "var Both = 1;\n",
        "use.js": "Both.toFixed();\n",
    },
    "alias-read": {
        "pub.js": PUBLISHER,
        "use.js": "const L = window.Lib;\nL.run();\nL.stop();\n",
    },
    "alias-escape": {
        "pub.js": PUBLISHER,
        "use.js": "const L = window.Lib;\nuse(L);\nL.run();\n",
    },
    "alias-global-this": {
        "pub.js": PUBLISHER,
        "use.js": "const L = globalThis.Lib;\nL.run();\n",
    },
    "destructure": {
        "pub.js": PUBLISHER,
        "use.js": "const { run, stop: halt } = window.Lib;\nrun();\nhalt();\n",
    },
    "destructure-unknown": {
        "pub.js": PUBLISHER,
        "use.js": "const { nope } = window.Lib;\nnope();\n",
    },
    "factory": {
        "pub.js": (
            "function make() { return { go, view: window.Other }; }\nfunction go() {}\n"
            "window.Make = make;\n"
        ),
        "use.js": "const m = window.make();\nm.go();\n",
    },
    "factory-published": {
        "pub.js": (
            "function create() { return { go }; }\nfunction go() {}\nwindow.Fac = { create };\n"
        ),
        "use.js": "const o = Fac.create();\no.go();\no.stop();\n",
    },
    "namespace": {
        "ns.js": "var NS;\n(function (NS) { NS.a = 1; })(NS || (NS = {}));\n",
        "use.js": "NS.a;\nNS.b();\nNS;\n",
    },
    "namespace-twice": {
        "a.js": "var NS;\n(function (NS) { NS.a = 1; })(NS || (NS = {}));\n",
        "b.js": "var NS = {};\n",
        "use.js": "NS.a;\n",
    },
    "root-escape": {"use.js": "foo(window);\nvar w = window;\nglobalThis['x'];\nwindow[k]();\n"},
    "unknown-write": {
        "pub.js": PUBLISHER,
        "bad.js": "window[name] = 1;\neval('Lib = 1');\nthis[k] = 2;\n",
        "use.js": "Lib.run();\n",
    },
    "opaque-effects": {
        "pub.js": "var o = {};\nwindow.Lib = o;\nLib.a = 1;\nObject.assign(Lib, {});\n",
        "use.js": "Lib.a;\n",
    },
    "syntax-error": {"pub.js": PUBLISHER, "use.js": "Lib.run();\nfunction (\n"},
    "require-loader": {
        "use.js": "var x = require('./pub');\nx.go();\nmodule.exports = {};\n",
        "pub.js": "exports.go = function () {};\n",
    },
    "es-module": {
        "pub.js": PUBLISHER,
        "mod.js": "import './pub';\nLib.run();\nexport const a = 1;\n",
    },
    "typescript-file": {"pub.js": PUBLISHER, "use.ts": "Lib.run();\ndocument.title;\n"},
    "shorthand-reference": {
        "pub.js": PUBLISHER,
        "use.js": "var o = { Lib };\nvar p = { Missing };\n",
    },
    "new-expression": {
        "pub.js": "function Widget() {}\nwindow.Ui = { Widget };\n",
        "use.js": "new Ui.Widget();\nnew Nope.Thing();\n",
    },
    "partial-config": {
        "pub.js": PUBLISHER,
        "use.js": "Lib.run();\ndocument.title;\n",
        "tsconfig.json": (
            '{"compilerOptions":{"allowJs":true,"rootDirs":["a"]},"include":["src"]}'
        ),
    },
    "no-lib": {
        "use.js": "document.title;\nArray.from([]);\n",
        "tsconfig.json": '{"compilerOptions":{"allowJs":true,"noLib":true},"include":["src"]}',
    },
    "lib-list": {
        "use.js": "document.title;\nMap;\nPromise.all([]);\n",
        "tsconfig.json": (
            '{"compilerOptions":{"allowJs":true,"lib":["es2015","es2017.object"]},'
            '"include":["src"]}'
        ),
    },
    "force-modules": {
        "pub.js": PUBLISHER,
        "use.js": "Lib.run();\n",
        "tsconfig.json": (
            '{"compilerOptions":{"allowJs":true,"moduleDetection":"force"},"include":["src"]}'
        ),
    },
    "nodenext": {
        "pub.js": PUBLISHER,
        "use.js": "Lib.run();\n",
        "tsconfig.json": (
            '{"compilerOptions":{"allowJs":true,"module":"nodenext"},"include":["src"]}'
        ),
    },
}

VENDOR_SOURCE = (
    '(function(__factory){if(typeof exports==="object"&&typeof module!=="undefined")'
    '{module.exports=__factory()}else if(typeof define==="function"&&define.amd)'
    '{define([],__factory)}else{var __root;if(typeof window!=="undefined")'
    '{__root=window}else if(typeof global!=="undefined"){__root=global}'
    'else if(typeof self!=="undefined"){__root=self}else{__root=this}'
    "__root.Vendor=__factory()}})(function(){return {};});\n"
)


def _provenance(source: str, version: str = "1.2.3", digest: str | None = None) -> str:
    sha = digest or hashlib.sha256(source.encode()).hexdigest()
    return (
        f"# vendor {version} browser bundle\n\n"
        f"Vendored from `vendor@{version}` (`dist/v.js`), https://example.org/vendor.\n"
        f"Bundle SHA-256: `{sha}`.\nSPDX license: `MIT`.\n"
    )


def _vendor_config(host: bool = True, extra: str = "") -> str:
    host_key = '"scriptHost":"classic-browser",' if host else ""
    providers = '"scriptProviders":[{"source":"vendor/v.js","provenance":"vendor/PROV.md"}]'
    return (
        '{"compilerOptions":{"allowJs":true},"include":["src"],'
        f'"archkeel":{{{host_key}{providers}{extra}}}}}'
    )


VENDORS: dict[str, dict[str, str]] = {
    "vendor": {
        "tsconfig.json": _vendor_config(),
        "vendor/v.js": VENDOR_SOURCE,
        "vendor/PROV.md": _provenance(VENDOR_SOURCE),
        "src/use.js": "Vendor.go();\nVendor;\nnew Vendor.Thing();\n",
    },
    "vendor-no-host": {
        "tsconfig.json": _vendor_config(host=False),
        "vendor/v.js": VENDOR_SOURCE,
        "vendor/PROV.md": _provenance(VENDOR_SOURCE),
        "src/use.js": "Vendor.go();\n",
    },
    "vendor-wrong-digest": {
        "tsconfig.json": _vendor_config(),
        "vendor/v.js": VENDOR_SOURCE,
        "vendor/PROV.md": _provenance(VENDOR_SOURCE, digest="0" * 64),
        "src/use.js": "Vendor.go();\n",
    },
    "vendor-collision": {
        "tsconfig.json": _vendor_config(),
        "vendor/v.js": VENDOR_SOURCE,
        "vendor/PROV.md": _provenance(VENDOR_SOURCE),
        "src/use.js": "Vendor.go();\n",
        "src/other.js": "window.Vendor = {};\n",
    },
    "vendor-loader-write": {
        "tsconfig.json": _vendor_config(),
        "vendor/v.js": VENDOR_SOURCE,
        "vendor/PROV.md": _provenance(VENDOR_SOURCE),
        "src/use.js": "Vendor.go();\nmodule.exports = {};\n",
    },
    "vendor-bad-provider": {
        "tsconfig.json": _vendor_config(extra=',"x":1'),
        "src/use.js": "Vendor.go();\n",
    },
}


def _write(root: Path, files: dict[str, str], under_src: bool = True) -> None:
    for name, text in files.items():
        keep = name == "tsconfig.json" or not under_src or "/" in name
        path = root / (name if keep else f"src/{name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if not (root / "tsconfig.json").exists():
        (root / "tsconfig.json").write_text(CONFIG, encoding="utf-8")


def _compare(native_binary: Path, root: Path) -> list[str]:
    request = _request(root, "app", "tsconfig.json")
    return _differences(native_binary, request)


@pytest.mark.parametrize("name", GRID)
def test_the_grid_equals_the_python_collector(
    native_binary: Path, tmp_path: Path, name: str
) -> None:
    _write(tmp_path, GRID[name])
    assert _compare(native_binary, tmp_path) == []


@pytest.mark.parametrize("name", VENDORS)
def test_vendored_libraries_equal_the_python_collector(
    native_binary: Path, tmp_path: Path, name: str
) -> None:
    _write(tmp_path, VENDORS[name], under_src=False)
    assert _compare(native_binary, tmp_path) == []


def test_mutated_projects_equal_the_python_collector(native_binary: Path, tmp_path: Path) -> None:
    rng = random.Random(4_3_5)
    names = list(GRID)
    found: list[str] = []
    for index in range(120):
        files = dict(GRID[names[index % len(names)]])
        victim = rng.choice([name for name in files if name.endswith((".js", ".ts"))])
        files[victim] = _mutate(rng, files[victim])
        root = tmp_path / f"m{index}"
        root.mkdir()
        _write(root, files)
        found += [f"m{index}: {line}" for line in _compare(native_binary, root)[:2]]
    assert found == []
