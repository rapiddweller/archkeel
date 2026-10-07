# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Snapshot scenarios retained from the former Node collector acceptance tests.

Each scenario preserves what the collector at commit 4e215679 wrote to disk before
collection; the differential compares the native frontend with that frozen reference.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

Content = str | bytes
# A symlink target: outside the snapshot (a path below the sibling directory), or verbatim.
Link = tuple[Literal["outside", "relative"], str]
NODENEXT: Final = {"module": "NodeNext", "moduleResolution": "NodeNext"}
HIDDEN: Final = {
    "src/main.js": "require('./hidden.cjs');",
    "src/hidden.cjs": "require('./main.js');",
}


@dataclass(frozen=True)
class Scenario:
    name: str
    files: dict[str, Content]
    # Replaces the default TSConfig keys one by one, the way the Node tests spread their overrides.
    config: dict[str, object] = field(default_factory=dict)
    roots: tuple[str, ...] = ("src",)
    links: dict[str, Link] = field(default_factory=dict)
    outside: dict[str, Content] = field(default_factory=dict)
    # The TSConfig path the request names; the file written is always `tsconfig.json`.
    tsconfig: str = "tsconfig.json"
    # TSConfig text written verbatim, for configurations the JSON default cannot express.
    raw_config: str | None = None


def manifest(**fields: object) -> str:
    return json.dumps(fields)


def only(*paths: str) -> dict[str, object]:
    return {"files": list(paths), "include": []}


def write(root: Path, scenario: Scenario) -> None:
    default = {"compilerOptions": NODENEXT, "include": ["src"], **scenario.config}
    files = {"tsconfig.json": scenario.raw_config or json.dumps(default), **scenario.files}
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())
    for rel, content in scenario.outside.items():
        target = root.parent / "outside" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())
    for rel, (kind, target) in scenario.links.items():
        link = root / rel
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(root.parent / "outside" / target if kind == "outside" else target)


def _module_require(index: int, source: str) -> Scenario:
    return Scenario(
        f"indirect-module-require-{index}",
        {"src/main.ts": source, "src/hidden.cjs": "module.exports = 7;\n"},
    )


def _factory(index: int, source: str, entry: str = "src/main.ts") -> Scenario:
    return Scenario(f"create-require-{index}", {entry: source})


_PKG = '{"name":"example","version":"1.0.0","types":"index.d.ts"}'
_MODE_FILES: Final = {
    "package.json": json.dumps(
        {
            "type": "module",
            "imports": {"#target": {"import": "./src/import.ts", "require": "./src/require.ts"}},
        }
    ),
    "src/import.ts": "export interface Value { a: string }",
    "src/require.ts": "export interface Value { b: string }",
}
_TYPES = (
    "import type { Uri } from 'vscode'; import type { Feature } from '@vendor/host/feature'; "
    "import type {} from '#local';"
)
_TYPES_FILES: Final = {
    "package.json": '{"name":"app","imports":{"#local":"./src/local.ts"}}',
    "src/local.ts": "export {};",
    "node_modules/@types/vscode/package.json": (
        '{"name":"@types/vscode","version":"1.0.0","types":"index.d.ts"}'
    ),
    "node_modules/@types/vscode/index.d.ts": "export interface Uri { path: string };",
    "node_modules/@types/vendor__host/package.json": (
        '{"name":"@types/vendor__host","version":"1.0.0","types":"index.d.ts"}'
    ),
    "node_modules/@types/vendor__host/feature.d.ts": "export interface Feature { name: string };",
}

SCENARIOS: Final[tuple[Scenario, ...]] = (
    *(
        _module_require(index, source)
        for index, source in enumerate(
            (
                "module.require.call(module, './hidden.cjs');\n",
                "const load = module.require; load('./hidden.cjs');\n",
                "const load = module.require; load.call(module, './hidden.cjs');\n",
                "module['require'].apply(module, ['./hidden.cjs']);\n",
            ),
            1,
        )
    ),
    Scenario(
        "literal-require-control",
        {"src/main.ts": "require('./hidden.cjs');\n", "src/hidden.cjs": "module.exports = 7;\n"},
    ),
    Scenario(
        "aliases-forms-and-runtime-closure",
        {
            "src/main.ts": (
                'import type { Value } from "@app/value";\nexport { value } from "./value.js";\n'
                'export * from "./extra.js";\ntype Loaded = import("./value.js").Value;\n'
                'import("./extra.js");\nimport host = require("./host.cjs");\n'
                'const x = require("./host.cjs");\n'
            ),
            "src/value.ts": "export interface Value { value: string }\nexport const value = 1;\n",
            "src/extra.ts": "export const extra = 1;\n",
            "src/host.d.cts": "declare const host: string[]; export = host;\n",
            "src/host.cjs": "const os = require('node:os'); module.exports = [os.platform()];\n",
        },
        {
            "compilerOptions": {**NODENEXT, "baseUrl": ".", "paths": {"@app/*": ["src/*"]}},
            "include": ["src"],
        },
    ),
    Scenario(
        "selected-scope-and-resolution-inputs",
        {
            "src/main.ts": "import '../shared/value.js';\n",
            "shared/value.ts": "export const value = 1;\n",
            "test/other.ts": "import 'missing';\n",
        },
        {"include": ["src", "test"]},
    ),
    Scenario(
        "computed-shadowed-unresolved",
        {
            "src/main.ts": (
                "require(variable);\nfunction f(require: Function) { require('./missing.js'); }\n"
                "import './not-here.js';\nimport(name);\n"
            )
        },
    ),
    Scenario(
        "syntax-and-config-errors",
        {"src/main.ts": "const = ;\n"},
        raw_config='{"extends":"../absent.json","include":["src"]}',
    ),
    Scenario(
        "declaration-without-runtime",
        {
            "src/main.ts": "import host = require('./host.cjs');",
            "src/host.d.cts": "declare const host: string; export = host;",
        },
    ),
    Scenario(
        "type-only-named-imports",
        {
            "src/main.ts": (
                "import { type Value } from './value.js'; export { type Value } from './value.js';"
            ),
            "src/value.d.ts": "export interface Value { value: string }",
        },
    ),
    Scenario(
        "esm-require-and-triple-slash",
        {
            "src/main.mts": (
                "/// <reference path='./other.d.ts' />\n"
                "const load = require; require('node:fs'); load(name);"
            ),
            "src/other.d.ts": "export {};",
        },
    ),
    Scenario(
        "external-package-in-snapshot",
        {
            "src/main.ts": "import 'example';",
            "node_modules/example/package.json": _PKG,
            "node_modules/example/index.d.ts": "export {};",
        },
    ),
    Scenario(
        "local-javascript-closure",
        {
            "src/main.ts": "import './runtime.js';",
            "src/runtime.js": "throw new Error('must not execute'); import './leaf.js';",
            "src/leaf.js": "import 'node:fs';",
        },
    ),
    *(
        Scenario(
            f"explicit-runtime-{runtime}-{state}",
            {
                "package.json": '{"type":"module"}',
                "src/main.mts": f"import './leaf.{runtime}';",
                f"src/leaf.{source}": "export const value = 1;",
                f"src/leaf.{runtime}": (
                    "throw new Error('must not execute'); "
                    + ("import('./missing.js');" if state == "gap" else "import('node:fs');")
                ),
            },
            {"compilerOptions": {**NODENEXT, "noEmit": True}, **only("src/main.mts")},
        )
        for runtime, source in (("js", "ts"), ("mjs", "mts"), ("cjs", "cts"))
        for state in ("gap", "complete")
    ),
    Scenario(
        "type-only-node-alias",
        {
            "src/main.ts": "import type { Value } from 'node:fs'; import 'node:fs';",
            "src/local.ts": "import './missing.js'; export type Value = string;",
        },
        {
            "compilerOptions": {
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "baseUrl": ".",
                "paths": {"node:fs": ["src/local.ts"]},
            },
            **only("src/main.ts"),
        },
    ),
    Scenario(
        "project-references",
        {"src/main.ts": "export {};"},
        {"references": [{"path": "../generated"}], "include": ["src"]},
    ),
    Scenario(
        "missing-tsconfig",
        {"src/main.ts": "export {};"},
        tsconfig="missing.json",
    ),
    Scenario(
        "local-require-declaration",
        {
            "src/main.ts": (
                "function require(name: string) { return name; } require('./leaf.js'); "
                "module['require']('./leaf.js');"
            ),
            "src/leaf.ts": "export {};",
        },
    ),
    Scenario(
        "resolver-symlink-outside",
        {"src/main.ts": "import './private.js';"},
        links={"src/private.ts": ("outside", "src/private.ts")},
        outside={"src/private.ts": "export const privateValue = 1;"},
    ),
    Scenario(
        "package-declarations-neighbor-runtime",
        {
            "src/main.ts": "import pkg = require('./pkg');",
            "src/pkg/package.json": '{"types":"types/index.d.ts","main":"runtime/entry.cjs"}',
            "src/pkg/types/index.d.ts": "declare const value: number; export = value;",
            "src/pkg/types/index.js": "module.exports = 1;",
            "src/pkg/runtime/entry.cjs": "require('../hidden.cjs');",
            "src/pkg/hidden.cjs": "require('../main.js');",
        },
        only("src/main.ts"),
    ),
    Scenario(
        "explicit-missing-tsconfig-files",
        {"src/main.ts": "export {};"},
        only("src/main.ts", "src/missing.ts"),
    ),
    _factory(
        1,
        "import { createRequire as factory } from 'node:module'; "
        "const load = factory(import.meta.url); load('./hidden.cjs');",
        "src/main.mts",
    ),
    _factory(
        2, "import * as mod from 'node:module'; const load = mod.createRequire(import.meta.url);"
    ),
    _factory(
        3,
        "const { createRequire: factory } = require('node:module'); "
        "const load = factory(__filename);",
    ),
    _factory(
        4,
        "const factory = require('node:module').createRequire; const load = factory(__filename);",
    ),
    Scenario(
        "create-require-ordinary",
        {"src/main.ts": "function createRequire(x: string) { return x; } createRequire('data');"},
    ),
    Scenario(
        "builtin-name-with-local-alias",
        {
            "src/main.ts": "import type { Value } from 'fs'; import 'node:fs';",
            "src/local.ts": "export type Value = string;",
        },
        {
            "compilerOptions": {
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "baseUrl": ".",
                "paths": {"fs": ["src/local.ts"]},
            },
            **only("src/main.ts"),
        },
    ),
    Scenario(
        "option-diagnostic-5110",
        {"src/main.ts": "export {};"},
        {"compilerOptions": {"module": "CommonJS", "moduleResolution": "NodeNext"}},
    ),
    Scenario(
        "options-valid",
        {"src/main.ts": "export {};"},
        {"compilerOptions": {**NODENEXT, "lib": ["ES2022"], "types": []}},
    ),
    *(
        Scenario(
            f"resolution-mode-{index}",
            {**_MODE_FILES, "src/main.mts": source},
            only("src/main.mts"),
        )
        for index, source in enumerate(
            (
                'type T = import("#target", { with: { "resolution-mode": "require" } }).Value;',
                'import type { Value } from "#target" with { "resolution-mode": "require" };',
                'import type { Value } from "#target" with { "resolution-mode": "import" };',
                'import type { Value } from "#target";',
            ),
            1,
        )
    ),
    *(
        Scenario(
            f"jsdoc-{kind}-{state}",
            {
                "src/main.js": comment + "\nexport const x = 1;",
                "src/hidden.js": (
                    "import './missing.js'; export const Value = 1;"
                    if state == "gap"
                    else "export const Value = 1;"
                ),
            },
            {
                "compilerOptions": {**NODENEXT, "allowJs": True, "checkJs": True},
                **only("src/main.js"),
            },
        )
        for kind, comment in (
            ("type", '/** @typedef {import("./hidden.js").Value} Value */'),
            ("tag", '/** @import {Value} from "./hidden.js" */'),
        )
        for state in ("gap", "complete")
    ),
    *(
        Scenario(
            f"module-bracket-{name}",
            {
                "src/main.mts": (
                    f"import * as mod from 'node:module'; const load = {access}(import.meta.url); "
                    "load('./hidden.cjs');"
                ),
                "src/hidden.cjs": "require('./main.mjs');",
            },
            only("src/main.mts"),
        )
        for name, access in (("literal", "mod['createRequire']"), ("computed", "mod[key]"))
    ),
    Scenario(
        "module-bracket-ordinary",
        {
            "src/main.mts": (
                "import * as mod from 'node:module'; mod['isBuiltin']('node:fs'); "
                "const plain = { createRequire() { return 1; } }; plain['createRequire']();"
            )
        },
    ),
    Scenario(
        "external-symlink-outside",
        {"src/main.ts": "import 'example';"},
        links={"node_modules/example": ("outside", "pkg")},
        outside={"pkg/package.json": _PKG, "pkg/index.d.ts": "export {};"},
    ),
    *(
        Scenario(
            f"workspace-symlink-{state}",
            {
                "src/main.ts": "import 'example';"
                if state != "type"
                else "import type {} from 'example';",
                "src/shared/package.json": manifest(
                    name="example", version="1.0.0", types="index.ts"
                ),
                "src/shared/index.ts": "import './hidden.js';",
                "src/shared/hidden.ts": "import './missing.js';"
                if state == "gap"
                else "export const value = 1;",
            },
            {
                "compilerOptions": {**NODENEXT, "preserveSymlinks": False},
                **only("src/main.ts"),
            },
            links={"node_modules/example": ("relative", "../src/shared")},
        )
        for state in ("gap", "value", "type")
    ),
    Scenario(
        "preserved-symlink-context",
        {
            "src/main.ts": "import 'example';",
            "src/shared/package.json": manifest(name="example", version="1.0.0", types="index.ts"),
            "src/shared/index.ts": "import 'dep';",
            "src/node_modules/dep/package.json": manifest(
                name="dep", version="1.0.0", types="index.ts"
            ),
            "src/node_modules/dep/index.ts": "export const version = 1;",
            "node_modules/dep/package.json": manifest(
                name="dep", version="2.0.0", types="index.ts"
            ),
            "node_modules/dep/index.ts": "export const version = 2;",
        },
        {"compilerOptions": {**NODENEXT, "preserveSymlinks": True}, **only("src/main.ts")},
        links={"node_modules/example": ("relative", "../src/shared")},
    ),
    Scenario(
        "explicit-file-roots",
        {
            "src/main.ts": "import hosts = require('../supportedHosts.cjs');",
            "supportedHosts.cjs": "module.exports = [require('node:os').platform()];",
            "supportedHosts.d.cts": "declare const hosts: readonly string[]; export = hosts;",
            "unselected.ts": "import './missing.js';",
        },
        roots=("src", "supportedHosts.cjs", "supportedHosts.d.cts"),
    ),
    *(
        Scenario(
            f"repository-wide-scope-{label}",
            {
                "src/main.ts": (
                    "import type { Thing } from 'lib'; import { value } from 'lib'; "
                    "export const use: Thing = value;"
                ),
                "node_modules/lib/package.json": (
                    '{"name":"lib","version":"1.0.0","types":"index.d.ts","main":"index.js"}'
                ),
                "node_modules/lib/index.d.ts": (
                    "export interface Thing { n: number }; export declare const value: Thing;"
                ),
                "node_modules/lib/index.js": "exports.value = { n: 1 };",
            },
            {"include": ["src/**/*.ts"], "exclude": ["node_modules"]},
            roots=roots,
        )
        for label, roots in (("src", ("src",)), ("dot", (".",)))
    ),
    *(
        Scenario(
            f"file-roots-beyond-include-{label}",
            {
                "src/main.ts": "export {};",
                "standalone.cjs": "require('./missing.cjs');",
                "standalone.ts": "export const value = 1;",
            },
            {"include": ["src"], "exclude": ["standalone.*"]},
            roots=roots,
        )
        for label, roots in (("ts", ("standalone.ts",)), ("cjs", ("src", "standalone.cjs")))
    ),
    *(
        Scenario(
            f"namespace-factory-{index}",
            {"src/main.cts": source},
        )
        for index, source in enumerate(
            (
                "const mod = require('node:module'); const load = mod.createRequire(__filename); "
                "load('./missing.cjs');",
                "const mod = require('node:module'); "
                "const load = mod['createRequire'](__filename); load('./missing.cjs');",
                "const mod = require('node:module'); const { createRequire: factory } = mod; "
                "const load = factory(__filename); load('./missing.cjs');",
                "import mod = require('node:module'); const load = mod.createRequire(__filename); "
                "load('./missing.cjs');",
                "const local = {createRequire: () => 1}; local.createRequire();",
            ),
            1,
        )
    ),
    *(
        Scenario(
            f"installed-declarations-{label}",
            {
                "src/main.ts": "import type { Value } from 'example';",
                "node_modules/example/package.json": _PKG,
                "node_modules/example/index.d.ts": "export interface Value { value: string };",
            },
            {"include": ["src", "node_modules/example/**/*.ts"], "exclude": []},
            roots=roots,
        )
        for label, roots in (
            ("dot", (".",)),
            ("explicit", ("src", "node_modules/example/index.d.ts")),
        )
    ),
    *(
        Scenario(
            f"external-runtime-identity-{label}",
            {**_TYPES_FILES, "src/main.ts": source},
        )
        for label, source in (
            ("value-alias", _TYPES.replace("import type {} from", "import") + ""),
            ("types", _TYPES),
        )
    ),
    *(
        Scenario(
            f"external-alias-{label}",
            {
                "package.json": manifest(
                    name="app", imports={"#host": "host-api", "#local": "./src/local.ts"}
                ),
                "src/main.ts": source,
                "src/local.ts": "export {};",
                "src/host.ts": "export {};",
                "node_modules/host-api/package.json": manifest(
                    name="host-api", version="1.0.0", main="index.js"
                ),
                "node_modules/host-api/index.js": "exports.value = 1;",
                "node_modules/@types/host-api/package.json": (
                    '{"name":"@types/host-api","version":"1.0.0","types":"index.d.ts"}'
                ),
                "node_modules/@types/host-api/index.d.ts": "export declare const value: number;",
            },
        )
        for label, source in (
            ("value", "import { value } from '#host'; import '#local';"),
            ("types", "import type {} from '#local';"),
            ("local-value", "import '#local';"),
        )
    ),
    *(
        Scenario(
            f"source-bytes-{label}",
            {"src/main.ts": data, "src/value.ts": "export const value = 1;\n"},
        )
        for label, data in (
            ("ff", b"// marker \xff\nimport './value.js';\n"),
            ("fe", b"// marker \xfe\nimport './value.js';\n"),
            ("utf8", "// marker café\nimport './value.js';\n".encode()),
        )
    ),
)


_VALUE: Final = "export const value = 1;\n"
_LIB_PATHS: Final = {"baseUrl": ".", "paths": {"@x/*": ["src/lib/*"]}}
_PACKAGE: Final = manifest(name="pkg", version="1.0.0")
# Each layout: the specifier, the files it names, and compiler options it needs.
_LAYOUTS: Final[dict[str, tuple[str, dict[str, str], dict[str, object]]]] = {
    "ts-file": ("./x", {"src/x.ts": _VALUE}, {}),
    "js-extension-for-ts": ("./x.js", {"src/x.ts": _VALUE}, {}),
    "js-file": ("./x.js", {"src/x.js": _VALUE}, {}),
    "extensionless-js": ("./x", {"src/x.js": _VALUE}, {}),
    "ts-extension": ("./x.ts", {"src/x.ts": _VALUE}, {}),
    "directory-index": ("./x", {"src/x/index.ts": _VALUE}, {}),
    "directory-slash": ("./x/", {"src/x/index.ts": _VALUE}, {}),
    "directory-index-js": ("./x/index.js", {"src/x/index.ts": _VALUE}, {}),
    "directory-types": (
        "./x",
        {"src/x/package.json": manifest(types="t.d.ts"), "src/x/t.d.ts": _VALUE},
        {},
    ),
    "directory-main": (
        "./x",
        {"src/x/package.json": manifest(main="m.js"), "src/x/m.ts": _VALUE},
        {},
    ),
    "file-before-directory": ("./x", {"src/x.ts": _VALUE, "src/x/index.ts": _VALUE}, {}),
    "module-extensions": ("./x.mjs", {"src/x.mts": _VALUE}, {}),
    "commonjs-extensions": ("./x.cjs", {"src/x.cts": _VALUE}, {}),
    "declaration": ("./x", {"src/x.d.ts": _VALUE}, {}),
    "declaration-js-extension": ("./x.js", {"src/x.d.ts": _VALUE}, {}),
    "dotted-stem": ("./x.y", {"src/x.y.ts": _VALUE}, {}),
    "json": ("./x.json", {"src/x.json": "{}"}, {}),
    "missing": ("./x", {}, {}),
    "paths-name": ("@x/y", {"src/lib/y.ts": _VALUE}, _LIB_PATHS),
    "paths-directory": ("@x/y", {"src/lib/y/index.ts": _VALUE}, _LIB_PATHS),
    "paths-extension": (
        "@x/y",
        {"src/lib/y.ts": _VALUE},
        {"baseUrl": ".", "paths": {"@x/*": ["src/lib/*.ts"]}},
    ),
    "base-url": ("lib/y", {"src/lib/y.ts": _VALUE}, {"baseUrl": "src"}),
    "package-types": (
        "pkg",
        {
            "node_modules/pkg/package.json": manifest(name="pkg", types="index.d.ts"),
            "node_modules/pkg/index.d.ts": _VALUE,
        },
        {},
    ),
    "package-main": (
        "pkg",
        {
            "node_modules/pkg/package.json": manifest(name="pkg", main="lib/index.js"),
            "node_modules/pkg/lib/index.js": _VALUE,
        },
        {},
    ),
    "package-index": (
        "pkg",
        {"node_modules/pkg/package.json": _PACKAGE, "node_modules/pkg/index.js": _VALUE},
        {},
    ),
    "package-subpath": (
        "pkg/sub",
        {"node_modules/pkg/package.json": _PACKAGE, "node_modules/pkg/sub.d.ts": _VALUE},
        {},
    ),
    "package-exports": (
        "pkg",
        {
            "node_modules/pkg/package.json": manifest(name="pkg", exports={".": "./index.js"}),
            "node_modules/pkg/index.js": _VALUE,
        },
        {},
    ),
    "package-types-only": ("pkg", {"node_modules/@types/pkg/index.d.ts": _VALUE}, {}),
    "package-empty": ("pkg", {"node_modules/pkg/package.json": _PACKAGE}, {}),
}
_SETTINGS: Final[dict[str, tuple[dict[str, object], dict[str, str]]]] = {
    "node10": ({"module": "CommonJS", "moduleResolution": "Node"}, {}),
    "nodenext-commonjs": (NODENEXT, {"package.json": "{}"}),
    "nodenext-module": (NODENEXT, {"package.json": '{"type":"module"}'}),
    "node16-module": (
        {"module": "Node16", "moduleResolution": "Node16"},
        {"package.json": '{"type":"module"}'},
    ),
    "bundler": ({"module": "ESNext", "moduleResolution": "Bundler"}, {}),
    "implied": ({}, {}),
}
_FORMS: Final = {
    "static": "import './x';",
    "dynamic": "import('./x');",
    "require": "require('./x');",
}


# The layouts whose answer depends on the importing file's module format.
_FORMAT_SENSITIVE: Final = (
    "ts-file",
    "js-extension-for-ts",
    "extensionless-js",
    "directory-index",
    "directory-main",
    "file-before-directory",
    "paths-name",
    "package-main",
)


def matrix() -> tuple[Scenario, ...]:
    """Every layout in every module setting, so a resolver more permissive than the compiler in
    any one setting shows up as a difference; the format-sensitive layouts also run as ESM and
    CommonJS entry files and as dynamic imports and `require` calls."""
    scenarios = []
    for setting, (options, base) in _SETTINGS.items():
        nodenext = setting.startswith(("nodenext", "node16"))
        for layout, (specifier, files, extra) in _LAYOUTS.items():
            entries = [("main.ts", "static")]
            if nodenext and layout in _FORMAT_SENSITIVE:
                entries += [
                    ("main.ts", "dynamic"),
                    ("main.ts", "require"),
                    ("main.mts", "static"),
                    ("main.cts", "static"),
                ]
            for entry, form in entries:
                scenarios.append(
                    Scenario(
                        f"matrix/{setting}/{layout}/{entry}-{form}",
                        {**base, **files, f"src/{entry}": _FORMS[form].replace("./x", specifier)},
                        {"compilerOptions": {**options, **extra}, **only(f"src/{entry}")},
                    )
                )
    return tuple(scenarios)


def _selection(name: str, config: dict[str, object], files: tuple[str, ...]) -> Scenario:
    """A TSConfig that selects among `files`; the whole snapshot is the source root."""
    return Scenario(
        f"selection/{name}",
        {path: "export {};\n" for path in files},
        {"compilerOptions": {**NODENEXT, "allowJs": True}, **config},
        roots=(".",),
    )


_TREE: Final = (
    "src/a.ts",
    "src/b.tsx",
    "src/c.d.ts",
    "src/d.mts",
    "src/e.cts",
    "src/e.cjs",
    "src/f.js",
    "src/f.ts",
    "src/g.js",
    "src/g.d.ts",
    "src/h.min.js",
    "src/gen/i.ts",
    "src/legacy/j.ts",
    "src/deep/k/l.ts",
    "src/deep/k/l.test.ts",
    "src/.hidden/m.ts",
    "src/.dot.ts",
    "src/node_modules/n/index.d.ts",
    "lib/o.ts",
    "outdir/p.ts",
    "node_modules/q/index.d.ts",
    "top.ts",
)
_BASE: Final = {"compilerOptions": {"module": "CommonJS", "moduleResolution": "Node"}}


def configurations() -> tuple[Scenario, ...]:
    """TSConfig features: which files are selected, and which options a chain of configs sets."""
    selections = {
        "default": {"include": None},
        "src-directory": {"include": ["src"]},
        "recursive-ts": {"include": ["src/**/*.ts"]},
        "shallow": {"include": ["src/*.ts"]},
        "tsx-only": {"include": ["src/**/*.tsx"]},
        "question-mark": {"include": ["src/?.ts"]},
        "exclude-tests": {"include": ["src"], "exclude": ["**/*.test.ts"]},
        "exclude-directory": {"include": ["src"], "exclude": ["src/legacy", "src/gen"]},
        "exclude-empty": {"include": ["src", "node_modules/q"], "exclude": []},
        "default-excludes": {"include": ["**/*"]},
        "out-dir": {"include": ["**/*"], "compilerOptions": {**NODENEXT, "outDir": "outdir"}},
        "files-and-include": {"files": ["top.ts"], "include": ["lib"]},
        "files-only": {"files": ["top.ts", "src/a.ts"]},
        "outside-include": {"include": ["../elsewhere/**/*.ts", "lib"]},
        "dotted-include": {"include": ["src/.hidden", "src/.dot.ts"]},
        "no-allow-js": {"include": ["src"], "compilerOptions": NODENEXT},
    }
    cases = [
        _selection(
            name,
            {k: v for k, v in config.items() if v is not None},
            _TREE,
        )
        for name, config in selections.items()
    ]
    chain = {
        "tsconfig.base.json": json.dumps(_BASE),
        "tsconfig.json": '{"extends": "./tsconfig.base", "include": ["src"]}',
        "src/main.ts": "import './x';",
        "src/x/index.ts": "export {};",
    }
    return (
        *cases,
        Scenario("extends/relative-options", chain, raw_config=chain["tsconfig.json"]),
        Scenario(
            "extends/array-later-wins",
            {
                "a.json": json.dumps({"compilerOptions": NODENEXT}),
                "b.json": json.dumps(_BASE),
                "src/main.ts": "import './x';",
                "src/x/index.ts": "export {};",
            },
            raw_config='{"extends": ["./a.json", "./b.json"], "include": ["src"]}',
        ),
        Scenario(
            "extends/include-from-base-directory",
            {
                "config/base.json": json.dumps({**_BASE, "include": ["../src"]}),
                "src/main.ts": "import './y';",
                "src/y.ts": "export {};",
            },
            raw_config='{"extends": "./config/base.json"}',
        ),
        Scenario(
            "extends/own-include-wins",
            {
                "base.json": json.dumps({**_BASE, "include": ["nowhere"]}),
                "src/main.ts": "export {};",
            },
            raw_config='{"extends": "./base.json", "include": ["src"]}',
        ),
        Scenario(
            "extends/paths-relative-to-base",
            {
                "configs/base.json": json.dumps(
                    {
                        "compilerOptions": {
                            **_BASE["compilerOptions"],
                            "paths": {"@l/*": ["../lib/*"]},
                        }
                    }
                ),
                "src/main.ts": "import '@l/a';",
                "lib/a.ts": "export {};",
            },
            raw_config='{"extends": "./configs/base", "include": ["src", "lib"]}',
            roots=("src", "lib"),
        ),
        Scenario(
            "extends/base-url-from-base",
            {
                "configs/base.json": json.dumps(
                    {"compilerOptions": {**_BASE["compilerOptions"], "baseUrl": "../src"}}
                ),
                "src/main.ts": "import 'lib/a';",
                "src/lib/a.ts": "export {};",
            },
            raw_config='{"extends": "./configs/base", "include": ["src"]}',
        ),
        Scenario(
            "extends/config-dir-template",
            {
                "configs/base.json": json.dumps({**_BASE, "include": ["${configDir}/src"]}),
                "src/main.ts": "export {};",
            },
            raw_config='{"extends": "./configs/base.json"}',
        ),
        Scenario(
            "extends/missing",
            {"src/main.ts": "export {};"},
            raw_config='{"extends": "./absent", "include": ["src"]}',
        ),
        Scenario(
            "extends/circular",
            {
                "a.json": '{"extends": "./b.json"}',
                "b.json": '{"extends": "./a.json"}',
                "src/main.ts": "export {};",
            },
            raw_config='{"extends": "./a.json", "include": ["src"]}',
        ),
        *(
            Scenario(
                f"extends/package-{state}",
                {
                    **(
                        {
                            "node_modules/@tsconfig/base/tsconfig.json": json.dumps(
                                {"compilerOptions": NODENEXT}
                            )
                        }
                        if state == "installed"
                        else {}
                    ),
                    "src/main.ts": "import './x.js';",
                    "src/x.ts": "export {};",
                },
                raw_config='{"extends": "@tsconfig/base/tsconfig.json", "include": ["src"]}',
            )
            for state in ("installed", "absent")
        ),
        Scenario(
            "config/nested-location",
            {
                "config/tsconfig.json": json.dumps({**_BASE, "include": ["../src"]}),
                "src/main.ts": "import './x';",
                "src/x.ts": "export {};",
            },
            tsconfig="config/tsconfig.json",
        ),
        Scenario(
            "config/comments-and-trailing-commas",
            {"src/main.ts": "import './x';", "src/x.ts": "export {};"},
            raw_config=(
                '{\n  // comment\n  "compilerOptions": {"module": "CommonJS", /* x */ '
                '"moduleResolution": "Node",},\n  "include": ["src",],\n}\n'
            ),
        ),
        Scenario(
            "config/case-insensitive-option-names",
            {"src/main.ts": "import './x';", "src/x/index.ts": "export {};"},
            raw_config=(
                '{"compilerOptions": {"Module": "CommonJS", "ModuleResolution": "node"}, '
                '"include": ["src"]}'
            ),
        ),
        Scenario(
            "config/paths-before-self-reference",
            {
                "package.json": manifest(name="app", exports={".": "./src/main.ts"}),
                "src/main.ts": "import 'app';",
                "src/lib.ts": "export {};",
            },
            {
                "compilerOptions": {
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "baseUrl": ".",
                    "paths": {"app": ["src/lib.ts"]},
                }
            },
        ),
    )
