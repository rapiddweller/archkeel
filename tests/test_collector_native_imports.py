# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340: the native TypeScript collector gives the same reply on each run, and never crashes.

Consumer: the core, which starts the collector. A reply must not depend on the order of a hash
map, and a deep or damaged source must give a reply and not end the process.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from collector_wire import collect, request_bytes

ROOT = Path(__file__).parents[1]
STUDIO_UI = "src/archkeel/studio/ui"
FIXTURES = (
    ("fixtures/H-typescript", "shop", "tsconfig.json"),
    ("fixtures/H-uml-typescript", "uml", "tsconfig.json"),
    ("fixtures/F-typescript-story", "demo", "tsconfig.json"),
    ("fixtures/L-nest-realworld", "nestjs.realworld", "tsconfig.build.json"),
    (".", "archkeel.studio.ui", f"{STUDIO_UI}/tsconfig.json"),
)


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


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")


def test_the_reply_is_the_same_bytes_on_every_run(native_binary: Path) -> None:
    # A hash map that leaked its order into a record or the source digest would show here: each
    # process seeds its hashes at random.
    for path, namespace, tsconfig in FIXTURES[3:]:
        scope = (STUDIO_UI,) if path == "." else ("src",)
        request = request_bytes(ROOT / path, namespace, tsconfig, roots=scope)
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
    # stops with a RecursionError long before this depth; AD-320 records that difference.
    (tmp_path / "tsconfig.json").write_text('{"include":["src"]}')
    (tmp_path / "src").mkdir()
    depth = 30_000
    (tmp_path / "src/deep.ts").write_text(
        'import a from "./a";\nconst x = ' + "[" * depth + "]" * depth + ";\nimport b from './b';\n"
    )
    facts = collect(native_binary, request_bytes(tmp_path, "app", "tsconfig.json"))
    assert len(facts["files"]) == 1


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
    facts = collect(native_binary, request_bytes(tmp_path, "app", "tsconfig.json"))
    assert len(facts["files"]) == len(_pathological())
