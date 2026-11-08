# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-319: the native collector extracts the same imports as the Python TypeScript collector.

Consumer: the host process port. The oracle is the Python collector in the legacy mode of the
native collector (`native_oracle`): the four producers that the native collector does not have are
off. Then the decoded files, inputs, evidence, import records, targets, gaps and coverage must be
equal, with no filter. The oracle is temporary: PR 4.3 deletes it.
"""

from __future__ import annotations

import dataclasses
import json
import os
import random
import subprocess
from pathlib import Path

import pytest
from native_oracle import legacy_facts

from archkeel.analyzer.process import ProcessCollector
from archkeel.ir.facts import SourceFacts
from archkeel.ir.facts_codec import encode_request
from archkeel.ir.protocol import (
    CollectionError,
    CollectionRequest,
    ProtocolVersion,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

ROOT = Path(__file__).parents[1]
STUDIO_UI = "src/archkeel/studio/ui"
FIXTURES = (
    ("fixtures/H-typescript", "shop", "tsconfig.json"),
    ("fixtures/H-uml-typescript", "uml", "tsconfig.json"),
    ("fixtures/F-typescript-story", "demo", "tsconfig.json"),
    ("fixtures/L-nest-realworld", "nestjs.realworld", "tsconfig.build.json"),
    (".", "archkeel.studio.ui", f"{STUDIO_UI}/tsconfig.json"),
)


def _plain(value: object) -> object:
    """Turn a decoded fact into JSON data, so that a difference prints as text."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(item) for item in value)
    entries = getattr(value, "entries", None)
    if entries is not None:
        return {key: _plain(item) for key, item in entries}
    return getattr(value, "value", value)


def _view(facts: SourceFacts) -> dict[str, object]:
    sections = {section.name.value: section.records for section in facts.sections}
    coverage = facts.coverage
    return {
        "files": _plain(facts.files),
        "inputs": _plain(facts.inputs),
        "source_digest": facts.source.source_digest,
        "scope": _plain(facts.source.scope),
        "targets": _plain(facts.imports),
        "imports": _plain(sections["imports"]),
        "unknowns": _plain(sections["unknowns"]),
        "gaps": _plain(coverage.gaps),
        "evidence": _plain(facts.evidence),
        "selected": list(coverage.selected_files),
        "read": coverage.files_read,
        "parsed": coverage.files_parsed,
        "full_scope": coverage.full_scope,
    }


def _request(
    root: Path,
    namespace: str,
    tsconfig: str,
    *,
    roots: tuple[str, ...] = ("src",),
    version: ProtocolVersion = ProtocolVersion.V8,
    exclude_test_sources: bool = False,
    bundler: bool = False,
) -> CollectionRequest:
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(roots, namespace, exclude_test_sources),
        TypeScriptSettings(tsconfig, bundler),
        version,
    )


def _differences(binary: Path, request: CollectionRequest) -> list[str]:
    native = ProcessCollector((str(binary),), protocol_version=ProtocolVersion.V8).collect(request)
    assert not isinstance(native, CollectionError), native
    oracle, scripts = legacy_facts(request)
    # A global script gets gaps that only the script analysis can give: the tree must hold none.
    assert scripts == (), f"the tree holds global scripts: {scripts}"
    mine, theirs = _view(native), _view(oracle)
    found: list[str] = []
    for key, value in mine.items():
        if value == theirs[key]:
            continue
        if isinstance(value, list) and isinstance(theirs[key], list):
            ours = {json.dumps(item, sort_keys=True) for item in value}
            other = {json.dumps(item, sort_keys=True) for item in theirs[key]}  # type: ignore[attr-defined]
            order = " (same set, other order)" if ours == other else ""
            found += [f"{key}: only native: {text[:240]}" for text in sorted(ours - other)[:2]]
            found += [f"{key}: only python: {text[:240]}" for text in sorted(other - ours)[:2]]
            found += [f"{key}: {len(value)} native, {len(theirs[key])} python{order}"]  # type: ignore[arg-type]
        else:
            found.append(f"{key}: {value!r} native, {theirs[key]!r} python")
    return found


@pytest.mark.parametrize(("path", "namespace", "tsconfig"), FIXTURES)
def test_fixture_imports_equal_the_python_collector(
    native_binary: Path, path: str, namespace: str, tsconfig: str
) -> None:
    root = ROOT / path
    scope = (STUDIO_UI,) if path == "." else ("src",)
    request = _request(root, namespace, tsconfig, roots=scope)
    assert _differences(native_binary, request) == []


# One tree for the resolution rules: relative names, `paths`, packages, `exports`, builtins.
PACKAGES = {
    "node_modules/pkg-a/package.json": '{"main":"main.js","types":"main.d.ts"}',
    "node_modules/pkg-a/main.d.ts": "",
    "node_modules/pkg-a/main.js": "",
    "node_modules/pkg-a/sub/deep.d.ts": "",
    "node_modules/pkg-b/package.json": (
        '{"exports":{".":{"types":"./index.d.ts","import":"./index.mjs","require":"./index.cjs"},'
        '"./sub":"./sub.js","./asset":"./a.css","./bad":"../x.js","./cond":{"node":"./n.js"}}}'
    ),
    "node_modules/pkg-b/index.d.ts": "",
    "node_modules/pkg-b/sub.d.ts": "",
    "node_modules/pkg-b/sub.js": "",
    "node_modules/pkg-b/a.css": "",
    "node_modules/@types/lodash/index.d.ts": "",
    "node_modules/@scope/pkg-c/package.json": '{"typesVersions":{"*":{"*":["ts/*"]}}}',
    "node_modules/@scope/pkg-c/index.d.ts": "",
    "node_modules/pkg-d/package.json": '{"exports":{"./*":"./*.js"}}',
    "node_modules/pkg-e/package.json": '{"exports":"./e.js"}',
    "node_modules/pkg-e/e.js": "",
    "node_modules/pkg-f/package.json": '{"exports":{"import":"./f.mjs","default":"./f.js"}}',
    "node_modules/pkg-f/f.mjs": "",
    "node_modules/pkg-f/f.js": "",
    "node_modules/pkg-h/package.json": '{"type":"module","main":"h"}',
    "node_modules/pkg-h/h.js": "",
    "node_modules/pkg-i/package.json": "{}",
    "node_modules/pkg-i/index.js": "",
    "node_modules/pkg-j/package.json": '{"exports":{"./a":null,"./b/*":"./b/*.js"}}',
    "node_modules/pkg-k/package.json": '{"exports":{".":{"weird":"./k.js"}}}',
    "node_modules/pkg-m/package.json": '{"exports":{".":"/abs.js","./a":"./a/../b.js"}}',
    "package.json": '{"name":"app","type":"module","exports":"./x.js"}',
}
SOURCES = {
    "src/util.ts": "",
    "src/util.js": "export {};\n",
    "src/dir/index.ts": "",
    "src/esm.mts": "",
    "src/cjs.cts": "",
    "src/pkgdir/package.json": '{"main":"./lib/entry.js"}',
    "src/pkgdir/lib/entry.ts": "",
    "src/data.json": "{}",
    "src/types.d.ts": "",
    "src/app/x.ts": "",
    "src/lib/index.ts": "",
    "src/only.js": "export {};\n",
    "src/badpkg/package.json": "{nope",
    "src/tv/package.json": '{"typesVersions":{"*":{"*":["x"]}}}',
    "src/tv/index.ts": "",
    "src/tests/helper.ts": "",
    "src/util.test.ts": "",
}
SPECIFIERS = (
    "./util ./util.js ./util.ts ./dir ./dir/ ./esm.js ./cjs.js ./pkgdir ./data ./data.json ./types "
    "./missing ../src/util . .. ./only ./badpkg ./tv @app/x @lib ~/util ~/dir pkg-a pkg-a/sub/deep "
    "pkg-b pkg-b/sub pkg-b/asset pkg-b/bad pkg-b/cond lodash lodash/fp @scope/pkg-c pkg-d/x pkg-e "
    "pkg-f pkg-h pkg-i pkg-j/a pkg-j/b/z pkg-k pkg-m pkg-m/a fs node:fs fs/promises node:test "
    "app app/sub #internal /abs/x nope-pkg ./tests/helper ./util.test ./style.css ./w?worker "
    "./pic.png ~/missing.css pkg-b/a.css"
).split()
CONFIGS = {
    "node10": (
        '{"compilerOptions":{"baseUrl":".","paths":{"@app/*":["src/app/*"],"@lib":["src/lib/index.ts"]},'
        '"resolveJsonModule":true,"module":"commonjs"},"include":["src"]}'
    ),
    "bundler": (
        '{"compilerOptions":{"module":"esnext","moduleResolution":"bundler",'
        '"paths":{"~/*":["./src/*"]}},"include":["src"]}'
    ),
    "nodenext": (
        '{"compilerOptions":{"module":"nodenext","moduleResolution":"nodenext"},"include":["src"]}'
    ),
    "blocked": '{"compilerOptions":{"rootDirs":["a"]},"include":["src"]}',
    "partial": '{"compilerOptions":{"nope":1},"include":["src"]}',
    "classic": (
        '{"compilerOptions":{"module":"es2015","moduleResolution":"classic"},"include":["src"]}'
    ),
}


COMMONJS = '{"compilerOptions":{"module":"commonjs","allowJs":true},"include":["src"]}'
BUNDLER_SRC = (
    '{"compilerOptions":{"module":"esnext","moduleResolution":"bundler"},"include":["src"]}'
)


def _imports_of(specifiers: list[str]) -> str:
    lines: list[str] = []
    for index, specifier in enumerate(specifiers):
        lines += [
            f'import a{index} from "{specifier}";',
            f'export * from "{specifier}";',
            f'const r{index} = require("{specifier}");',
            f'const d{index} = import("{specifier}");',
            f'type T{index} = import("{specifier}").X;',
            f'import type {{ Y{index} }} from "{specifier}";',
        ]
    return "\n".join(lines) + "\n"


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")


@pytest.mark.parametrize("name", CONFIGS)
def test_resolution_rules_equal_the_python_collector(
    tmp_path: Path, native_binary: Path, name: str
) -> None:
    importer = _imports_of(SPECIFIERS)
    files = {
        **PACKAGES,
        **SOURCES,
        "tsconfig.json": CONFIGS[name],
        "src/importer.ts": importer,
        "src/importer.mts": importer,
        "src/importer.cts": importer,
        "src/sub/deep.ts": _imports_of(["./x", "../util", "pkg-a", "@app/x"]),
    }
    _write(tmp_path, files)
    for bundler in (False, True):
        for exclude in (False, True):
            version = ProtocolVersion.V9 if exclude else ProtocolVersion.V8
            request = _request(
                tmp_path,
                "app",
                "tsconfig.json",
                version=version,
                exclude_test_sources=exclude,
                bundler=bundler,
            )
            found = _differences(native_binary, request)
            assert found == [], f"{name} bundler={bundler} exclude_tests={exclude}"


@pytest.mark.parametrize("form", ["import", "require"])
def test_a_commonjs_tree_resolves_like_the_python_collector(
    tmp_path: Path, native_binary: Path, form: str
) -> None:
    files = {
        "tsconfig.json": COMMONJS,
        "src/a.js": 'const b = require("./b");\nconst c = require("./c.js");\n',
        "src/b.js": "module.exports = 1;\nexport {};\n",
        "src/c.ts": "export const c = 1;\n",
        "src/d.ts": ("import e = require" if form == "import" else "const e = require")
        + '("./a");\n',
    }
    _write(tmp_path, files)
    assert _differences(native_binary, _request(tmp_path, "app", "tsconfig.json")) == []


# Snippets that a real file holds, and fragments that no grammar accepts.
PIECES = (
    'import a from "./util";',
    "import { b, type C } from './dir';",
    'import type { D } from "./types";',
    'import * as ns from "pkg-a";',
    'import "./side-effect";',
    'import e = require("./cjs");',
    'export * from "./esm";',
    'export { h } from "./util.js";',
    'export type { I } from "./types";',
    'const k = await import("./lib");',
    'type L = import("./app/x").L;',
    'let m: typeof import("./util");',
    'const n = require("./only");',
    "const o = require(variable);",
    "const q = import(`./q/${r}`);",
    'import(/* c */ "./util");',
    'import s2 from "./esc\\u0041";',
    'import w from "./w" with { "resolution-mode": "require" };',
    "if (x) { require('./util'); }",
    "const r = require; r('./util');",
    "const { require: q2 } = module;",
    'const m2 = require("module");',
    "/** @import { T } from './t' */",
    '/// <reference path="./types.d.ts" />',
    "/** @type {import('./util').X} */",
    "function f(x: import('./app/x').T) {}",
    "const y = z as import('./lib').V;",
    "const t = <div>{require('./util')}</div>;",
    "class A<T extends import('./util').B> {}",
    "export default function () {}",
    "import { unterminated from './util';",
    "const ( = ;",
    "}} {{ ))",
    'import("',
    "/* unterminated",
    "`unterminated ${",
    "﻿",
    "😀 import a from './😀';",
)
SEPARATORS = ("\n", "\r\n", " ", " ", "\r", "\n\n  ")


def _random_source(rng: random.Random) -> str:
    text = ""
    for _ in range(rng.randint(1, 8)):
        text += rng.choice(PIECES) + rng.choice(SEPARATORS)
    if rng.random() < 0.3:
        text = text[: rng.randint(0, len(text))]
    if rng.random() < 0.2:
        cut = rng.randint(0, len(text))
        text = (
            text[:cut] + rng.choice(["\x00", "�", "\\", "'", '"', "`", "{", "(", "<"]) + text[cut:]
        )
    return text


def test_random_sources_equal_the_python_collector(tmp_path: Path, native_binary: Path) -> None:
    rng = random.Random(880)
    files = {
        **SOURCES,
        "tsconfig.json": COMMONJS,
    }
    for index in range(240):
        suffix = rng.choice([".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"])
        # A JavaScript file without module syntax is a global script, which the oracle refuses.
        head = "export {};\n" if suffix in (".js", ".jsx") else ""
        files[f"src/fuzz/f{index}{suffix}"] = head + _random_source(rng)
    _write(tmp_path, files)
    found = _differences(native_binary, _request(tmp_path, "app", "tsconfig.json"))
    assert found == []


def _links(root: Path, outside: Path) -> None:
    os.symlink("real.ts", root / "src/link.ts")
    os.symlink("dir", root / "src/dirlink")
    os.symlink("loop.ts", root / "src/loop.ts")
    os.symlink(outside / "secret.ts", root / "src/escape.ts")
    os.symlink("../vendor/linked-pkg", root / "node_modules/linked-pkg")
    os.symlink(outside, root / "node_modules/escaping-pkg")


@pytest.mark.skipif(os.name == "nt", reason="a symlink needs a privilege on Windows")
def test_symlinks_and_package_metadata_equal_the_python_collector(
    tmp_path: Path, native_binary: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.ts").write_text("export const s = 1;\n")
    (outside / "package.json").write_text('{"main":"secret.ts"}')
    root = tmp_path / "repo"
    imports = ["./link", "./dirlink/x", "./escape", "./loop", "bad-json", "not-object"]
    imports += ["linked-pkg", "escaping-pkg", "node_json_bom", "typed-array", "typed-null"]
    _write(
        root,
        {
            "tsconfig.json": BUNDLER_SRC,
            "src/real.ts": "export const r = 1;\n",
            "src/dir/x.ts": "export const x = 1;\n",
            "src/main.ts": _imports_of(imports),
            "node_modules/bad-json/package.json": "{nope",
            "node_modules/not-object/package.json": "[1]",
            "node_modules/node_json_bom/package.json": '\ufeff{"main":"i.js"}',
            "node_modules/node_json_bom/i.js": "",
            "node_modules/typed-array/package.json": '{"types":["a.d.ts"],"main":3}',
            "node_modules/typed-null/package.json": '{"exports":null,"main":null}',
            "vendor/linked-pkg/package.json": '{"main":"index.js"}',
            "vendor/linked-pkg/index.js": "",
        },
    )
    _links(root, outside)
    request = _request(root, "app", "tsconfig.json")
    assert _differences(native_binary, request) == []
    # The cases are real: a link inside the snapshot resolves to its target, a link out of it is a
    # gap, and a package.json that is not an object or not JSON is a gap with its path.
    native = ProcessCollector((str(native_binary),), protocol_version=ProtocolVersion.V8).collect(
        request
    )
    assert isinstance(native, SourceFacts)
    titles = {gap.title for gap in native.coverage.gaps}
    assert "Resolver symlink outside snapshot" in titles
    assert "Package metadata is not valid JSON: node_modules/bad-json/package.json" in titles
    assert "Package metadata is not an object: node_modules/not-object/package.json" in titles
    files = {getattr(target, "file", None) for target in native.imports}
    assert {"src/real.ts", "src/dir/x.ts"} <= files


def test_the_reply_is_the_same_bytes_on_every_run(native_binary: Path) -> None:
    # A hash map that leaked its order into a record or the source digest would show here: each
    # process seeds its hashes at random.
    for path, namespace, tsconfig in FIXTURES[3:]:
        scope = (STUDIO_UI,) if path == "." else ("src",)
        request = encode_request(_request(ROOT / path, namespace, tsconfig, roots=scope))
        replies = {
            subprocess.run(
                [str(native_binary)],
                input=request,
                capture_output=True,
                check=True,
                cwd=ROOT / path,
            ).stdout
            for _ in range(4)
        }
        assert len(replies) == 1, path


def test_deep_nesting_gives_a_result(tmp_path: Path, native_binary: Path) -> None:
    # The walk of the tree is iterative, so nesting cannot overflow the stack. The Python collector
    # stops with a RecursionError long before this depth; AD-319 records that difference.
    (tmp_path / "tsconfig.json").write_text('{"include":["src"]}')
    (tmp_path / "src").mkdir()
    depth = 30_000
    (tmp_path / "src/deep.ts").write_text(
        'import a from "./a";\nconst x = ' + "[" * depth + "]" * depth + ";\nimport b from './b';\n"
    )
    native = ProcessCollector((str(native_binary),), protocol_version=ProtocolVersion.V8)
    facts = native.collect(_request(tmp_path, "app", "tsconfig.json"))
    assert isinstance(facts, SourceFacts), facts
    assert len(facts.files) == 1


def _pathological() -> dict[str, bytes]:
    return {
        "nul.ts": b"import a from './a\x00b';\x00\x00",
        "binary.ts": bytes(range(256)) * 40,
        "invalid-utf8.ts": b"import a from './\xff\xfe\xc3(';\nimport b from './b';",
        "deep-parens.ts": b"const a = " + b"(" * 3000 + b"1" + b")" * 3000 + b";",
        "deep-arrays.ts": b"const a = " + b"[" * 3000 + b"]" * 3000 + b";",
        "deep-types.ts": b"type T = " + b"Array<" * 1500 + b"number" + b">" * 1500 + b";",
        "deep-blocks.ts": b"{" * 2500 + b"}" * 2500,
        "long-line.ts": b"import a from './" + b"x" * 2_000_000 + b"';",
        "many-imports.ts": b"".join(b'import a%d from "./m%d";\n' % (n, n) for n in range(5000)),
        "unclosed-string.ts": b'import a from "./a',
        "unclosed-comment.ts": b"/** @import {T} from './t' ",
        "unclosed-template.ts": b"const a = `${`${`${",
        "lone-bytes.ts": b"\xe2\x80" + b"\n" + b"\xe2\x80\xa8" + b"\r",
        "jsdoc-storm.js": b"/**" + b" @type {" * 4000 + b"import('./a')" + b"} " * 4000 + b"*/",
        "empty.ts": b"",
    }


def test_pathological_sources_do_not_crash_the_native_collector(
    tmp_path: Path, native_binary: Path
) -> None:
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"allowJs":true},"include":["src"]}'
    )
    (tmp_path / "src").mkdir()
    for name, data in _pathological().items():
        (tmp_path / "src" / name).write_bytes(data)
    request = _request(tmp_path, "app", "tsconfig.json")
    native = ProcessCollector((str(native_binary),), protocol_version=ProtocolVersion.V8)
    facts = native.collect(request)
    assert not isinstance(facts, CollectionError), facts
    assert len(facts.files) == len(_pathological())
