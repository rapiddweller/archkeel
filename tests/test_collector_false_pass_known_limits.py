# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Release blockers from the known-limits audit. Land each probe with its fix."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from boundary_types_plants import Plant as BoundaryPlant
from boundary_types_sources import project as boundary_project
from core_support import run
from corpus_support import commit_tree
from python_interface_plants import Plant, build
from rust_orphan_plants import OPEN_TRAIT_FORMS, OPEN_VALUE_FORMS
from rust_repository import APP, CRATE_RULES, component, repository, rule, validate
from test_collector_false_pass_sources import BASE

from archkeel.cli import core_only


def _open(issue: int) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"False PASS: #{issue}")


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _honest(document: dict[str, Any], identifier: str) -> None:
    rows = document["frame"]["rules"]
    if identifier not in rows or document.get("refusal"):
        raise ValueError(f"The plant did not produce its rule: {document}")
    assert rows[identifier][1] in {"FAIL", "UNKNOWN"}, document


NO_A_TO_B = rule(
    "NO-A-TO-B",
    "forbidden_dependency",
    source="native.app.a",
    target="native.app.b",
    include_type_checking=True,
)


@pytest.mark.parametrize(
    "files",
    [
        *[
            pytest.param(files, marks=_open(1515), id=f"value-{name}")
            for name, files in OPEN_VALUE_FORMS.items()
        ],
        *[
            pytest.param(files, marks=_open(1516), id=f"trait-{name}")
            for name, files in OPEN_TRAIT_FORMS.items()
        ],
        pytest.param(
            {
                "lib.rs": "pub mod a; pub mod b; pub mod c;\npub extern crate self as name;\n",
                "a.rs": "pub fn f() { crate::c::other::b::g(); }\n",
                "b.rs": "pub fn g() {}\n",
                "c.rs": "pub use crate::name as other;\n",
            },
            marks=_open(1517),
            id="re-exported-root-alias",
        ),
    ],
)
def test_rust_hidden_dispatch_cannot_pass(
    tmp_path: Path, release_core: Path, files: dict[str, str]
) -> None:
    """A hidden impl needs a named gap when its caller cannot be proved."""
    root = repository(
        tmp_path / "repo",
        release_core,
        {f"crates/app/src/{name}": text for name, text in files.items()},
        rules=(*CRATE_RULES, NO_A_TO_B),
    )
    _honest(validate(root), "NO-A-TO-B")


@_open(1517)
def test_a_re_exported_crate_root_cannot_hide_a_module(tmp_path: Path, release_core: Path) -> None:
    """A root re-export must not lose the module at the end of the path."""
    forbidden = rule(
        "NO-A-TO-HIDDEN",
        "forbidden_dependency",
        source="native.app.a",
        target="native.base_crate.hidden",
        include_type_checking=True,
    )
    root = repository(
        tmp_path / "repo",
        release_core,
        {
            "crates/base/src/lib.rs": "pub mod hidden;\n",
            "crates/base/src/hidden.rs": "pub fn g() {}\n",
            "crates/app/src/lib.rs": "pub mod a; pub mod c;\n",
            "crates/app/src/a.rs": "pub fn f() { crate::c::other::hidden::g(); }\n",
            "crates/app/src/c.rs": "pub use base_crate as other;\n",
        },
        rules=(*CRATE_RULES, forbidden),
    )
    _honest(validate(root), "NO-A-TO-HIDDEN")


@_open(1515)
def test_a_foreign_trait_glob_cannot_hide_an_anchored_impl(
    tmp_path: Path, release_core: Path
) -> None:
    """A glob-imported external trait can run an impl of a scanned type."""
    root = repository(
        tmp_path / "repo",
        release_core,
        {
            "crates/app/Cargo.toml": APP + 'trait-ext = { path="../../vendor/trait-ext" }\n',
            "crates/app/src/lib.rs": "mod a; mod b; mod c;\n",
            "crates/app/src/a.rs": "use trait_ext::*;\npub fn f()->u8 { crate::c::make().m() }\n",
            "crates/app/src/b.rs": "pub struct Y;\n"
            "impl trait_ext::T for Y { fn m(&self)->u8 { 1 } }\n",
            "crates/app/src/c.rs": "pub fn make()->crate::b::Y { crate::b::Y }\n",
            "vendor/trait-ext/Cargo.toml": '[package]\nname="trait-ext"\nversion="0.0.0"\n'
            'edition="2021"\n[workspace]\n',
            "vendor/trait-ext/src/lib.rs": "pub trait T { fn m(&self)->u8; }\n",
        },
        rules=(*CRATE_RULES, NO_A_TO_B),
    )
    _honest(validate(root), "NO-A-TO-B")


TS_FORMS = {
    "event-target": (
        1524,
        "const k = ['op','en'].join('');\n"
        "addEventListener('load', ev => { ev.target[k] = () => {}; });",
    ),
    "event-src-element": (
        1524,
        "const k = ['op','en'].join('');\n"
        "addEventListener('load', ev => { ev.srcElement[k] = () => {}; });",
    ),
    "this-double-alias": (
        1524,
        "const k = ['op','en'].join('');\n"
        "class C { m() { let a: any = this; let b = a; b[k] = () => {}; } }\n"
        "addEventListener('load', new C().m);",
    ),
    "super-result": (
        1524,
        "const k = ['op','en'].join('');\n"
        "class C extends EventTarget { m() { const s: any = super.valueOf(); "
        "s[k] = () => {}; } }\naddEventListener('load', new C().m);",
    ),
    "this-argument": (
        1524,
        "const k = ['op','en'].join('');\n"
        "function g(w: any) { w[k] = () => {}; }\nclass C { m() { g(this); } }\n"
        "addEventListener('load', new C().m);",
    ),
    "window-parameter": (
        1524,
        "const k = ['op','en'].join('');\n"
        "function f(w: any) { w[k] = () => {}; }\n"
        "addEventListener('load', ev => f(ev.target));",
    ),
    "window-result": (
        1524,
        "const k = ['op','en'].join('');\n"
        "function f(ev: any) { return ev.target; }\n"
        "addEventListener('load', ev => { f(ev)[k] = () => {}; });",
    ),
    "window-property": (
        1524,
        "const k = ['op','en'].join('');\n"
        "addEventListener('load', ev => { const h = { w: ev.target as any }; "
        "h.w[k] = () => {}; });",
    ),
    "lookup-stored": (
        1525,
        "export function run(o: any, k: string, t: string) { const f = o[k]; f(t)(); }",
    ),
    "lookup-passed": (
        1525,
        "function g(f: any, t: string) { f(t)(); }\n"
        "export function run(o: any, k: string, t: string) { g(o[k], t); }",
    ),
    "lookup-argument": (
        1525,
        "export function run(o: any, k: string, t: string) "
        "{ Function.prototype.call.call(o[k], null, t)(); }",
    ),
    "open-result": (
        1526,
        "const k = ['op','en'].join('');\nconst w = open('', '_self');\n(w as any)[k] = () => {};",
    ),
    "document-open": (1526, "const d = document.open();\nd.write('<script>open=()=>{}</script>');"),
    "link-click": (
        1526,
        "const el = document.createElement('a');\n"
        "el.href = ['java','script:open=()=>{}'].join('');\nel.click();",
    ),
    "prototype": (
        1527,
        "Object.defineProperty(EventTarget.prototype, 'dispatchEvent', {value: () => true});",
    ),
}
UNREAD = {
    "vue": '<script>import "../b/t";</script>',
    "svelte": '<script>import "../b/t";</script>',
    "astro": '---\nimport "../b/t";\n---\n<div/>',
    "mdx": 'import { T } from "../b/t";\n\n# Example\n',
    "html": '<script type="module">import "../b/t";</script>',
    "es6": 'import "../b/t";\n',
}


@pytest.mark.parametrize(
    ("files", "use"),
    [
        *[
            pytest.param(
                {"src/b/b.ts": "export {};\n" + text},
                "window.dispatchEvent(new Event('audit'));"
                if name == "prototype"
                else "window.open();",
                marks=_open(issue),
                id=name,
            )
            for name, (issue, text) in TS_FORMS.items()
        ],
        *[
            pytest.param(
                {f"src/a/hidden.{extension}": text},
                "export const a = 1;",
                marks=_open(1528),
                id=f"unread-{extension}",
            )
            for extension, text in UNREAD.items()
        ],
        pytest.param(
            {
                "src/a/package.json": '{"name":"owner","version":"1.0.0"}',
                "src/a/node_modules/local/package.json": '{"name":"local","main":"index.ts"}',
                "src/a/node_modules/local/index.ts": 'import "../../../b/t";\n'
                "export const hidden = 1;",
            },
            "import { hidden } from 'local';",
            marks=_open(1529),
            id="installed-package",
        ),
        pytest.param(
            {
                "src/b/b.ts": "export function hidden() {}\n",
                "boot.ts": "import {hidden} from './src/b/b';\nwindow.open = hidden as any;\n",
            },
            "window.open();",
            marks=_open(1546),
            id="outside-roots-writer",
        ),
    ],
)
def test_typescript_hidden_dependency_cannot_pass(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    files: dict[str, str],
    use: str,
) -> None:
    """An unproved global write or omitted source must hold the dependency rule."""
    root = tmp_path / "repo"
    _write(root, {**BASE, "src/a/a.ts": use, **files})
    commit_tree(root)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    _honest(run("validate", "--root", str(root))[1], "REQUIRES")


PYTHON = [
    pytest.param(
        "from plugin_vendor import load\nload('app.lib')\n",
        {
            "vendor/plugin_vendor.py": "from importlib import import_module\n"
            "def load(name):\n    import_module(name)\n"
        },
        marks=_open(1519),
        id="third-party-loader",
    ),
    pytest.param(
        "def f(provider):\n    code = provider.code\n    code.interact()\n",
        {
            "vendor/plugin_vendor.py": "class Loader:\n"
            "    def interact(self):\n        from importlib import import_module\n"
            "        import_module('app.lib')\n"
            "class Provider:\n    code = Loader()\nprovider = Provider()\n",
            "outside.py": "from plugin_vendor import provider\n"
            "from app.consumer import f\nf(provider)\n",
        },
        marks=_open(1520),
        id="unknown-provider",
    ),
    pytest.param(
        "from plugin_vendor import namespace\nkey = ''.join(['__im','port__'])\n"
        "namespace()[key]('app.lib')\n",
        {
            "vendor/plugin_vendor.py": "from builtins import __import__\n"
            "def namespace(): return globals()\n"
        },
        marks=_open(1521),
        id="library-globals",
    ),
]


@pytest.mark.parametrize(("consumer", "files"), PYTHON)
def test_python_hidden_import_cannot_pass(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    consumer: str,
    files: dict[str, str],
) -> None:
    """An unproved external value can invoke a loader without a written import."""
    root = tmp_path / "repo"
    root.mkdir()
    build(
        root,
        Plant(
            "loader", consumer, ("app.lib",), {"src/app/lib/__init__.py": "value = 1\n", **files}
        ),
    )
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["rules"] = [
        rule(
            "NO-IMPORT",
            "forbidden_dependency",
            source="app.consumer",
            target="app.lib",
            include_type_checking=True,
        )
    ]
    contract["rules"][0]["provenance"] = ["docs/target.md"]
    path.write_text(json.dumps(contract))
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    _honest(run("validate", "--root", str(root))[1], "NO-IMPORT")


@_open(1522)
def test_an_outside_package_writer_cannot_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An outside writer can replace a public re-export with a private function."""
    root = tmp_path / "repo"
    root.mkdir()
    build(
        root,
        Plant(
            "writer",
            "from app.lib import f\n",
            ("app.lib.pub",),
            {
                "src/app/lib/__init__.py": "from app.lib.pub import f\n",
                "src/app/lib/pub.py": "def f(): return 'public'\n",
                "src/app/lib/_priv.py": "def secret(): return 'private'\n",
                "outside.py": "from app.lib._priv import secret\nimport app.lib\n"
                "app.lib.f = secret\nimport app.consumer\n"
                "assert app.consumer.f() == 'private'\n",
            },
        ),
    )
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    _honest(run("validate", "--root", str(root))[1], "BOUNDARY")


@_open(1522)
def test_a_native_package_writer_cannot_pass(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A native extension can change a binding without handing in a module object."""
    root = tmp_path / "repo"
    root.mkdir()
    build(
        root,
        Plant(
            "native-writer",
            "import native_patch\nfrom app.lib import f\n",
            ("app.lib.pub",),
            {
                "src/app/lib/__init__.py": "from app.lib.pub import f\n",
                "src/app/lib/pub.py": "def f(): return 'public'\n",
                "src/app/lib/_priv.py": "def secret(): return 'private'\n",
                "vendor/native_patch.c": "#include <Python.h>\n"
                "static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "
                '"native_patch", NULL, -1, NULL};\n'
                "PyMODINIT_FUNC PyInit_native_patch(void) {\n"
                '    PyObject *lib = PyImport_ImportModule("app.lib");\n'
                '    PyObject *priv = PyImport_ImportModule("app.lib._priv");\n'
                "    if (!lib || !priv) return NULL;\n"
                '    PyObject *secret = PyObject_GetAttrString(priv, "secret");\n'
                '    if (!secret || PyObject_SetAttrString(lib, "f", secret) < 0) return NULL;\n'
                "    Py_DECREF(secret); Py_DECREF(priv); Py_DECREF(lib);\n"
                "    return PyModule_Create(&module);\n}\n",
            },
        ),
    )
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    _honest(run("validate", "--root", str(root))[1], "BOUNDARY")


@pytest.mark.parametrize(
    "slots",
    [
        pytest.param(True, marks=_open(1523), id="slots"),
        pytest.param(False, marks=_open(1523), id="outside-class-write"),
    ],
)
def test_lazy_class_annotations_cannot_pass_an_unproved_native_allowance(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch, slots: bool
) -> None:
    """A slot or outside write can change the value of a lazy class annotation."""
    body = "class Hidden:\n    pass\nclass Box:\n"
    if slots:
        body += "    __slots__ = ('object',)\n"
    body += "    def f(self, x: object) -> int: return 1\n__all__ = ['Box']\n"
    root = boundary_project(
        tmp_path / "repo",
        BoundaryPlant(
            body,
            "FAIL",
            allowed=(
                {
                    "qualified_name": "app.api.Box.f",
                    "position": "x",
                    "field_path": "",
                    "annotation": "object",
                },
            ),
        ),
    )
    if not slots:
        _write(root, {"outside.py": "import app.api\napp.api.Box.object = app.api.Hidden\n"})
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    _honest(run("validate", "--root", str(root))[1], "API-TYPES")


@_open(1518)
def test_an_outside_registry_override_cannot_certify_a_derive(
    tmp_path: Path, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source replacement can change the expansion without changing its lock identity."""
    fixture = json.loads(Path(__file__).with_name("false_pass_registry.json").read_text())
    root = repository(
        tmp_path / "repo",
        release_core,
        {
            "crates/app/Cargo.toml": fixture["manifest"],
            "crates/Cargo.lock": fixture["lock"],
            "crates/app/src/lib.rs": "pub mod a; pub mod b;\n",
            "crates/app/src/a.rs": "use serde::Serialize;\n#[derive(Serialize)]\npub struct S;\n",
            "crates/app/src/b.rs": "pub const fn secret() {}\n",
        },
        components=(component("base", "base_crate"), component("app", "app")),
        rules=(*CRATE_RULES, NO_A_TO_B),
    )
    home = tmp_path / "home"
    _write(
        home,
        {
            "config.toml": '[source.crates-io]\nreplace-with="synthetic"\n'
            f'[source.synthetic]\ndirectory="{tmp_path / "replacement"}"\n'
        },
    )
    _write(tmp_path / "replacement", fixture["vendor"])
    monkeypatch.setenv("CARGO_HOME", str(home))
    _honest(validate(root), "NO-A-TO-B")
