# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Real guarded source sites and compiler input grammar compatibility."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
SITES = [
    [
        "archkeel.analyzer.typescript.collect._Collection._observe",
        "if content is not None and self._selected(rel) and rel.endswith(_SOURCE):",
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._references",
        'rel.endswith((".cjs", ".cts"))',
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._target",
        'if not reference.type_only and specifier.startswith("node:") and is_builtin(specifier):',
    ],
    ["archkeel.analyzer.typescript.collect._Collection._local", 'if specifier.startswith("#"):'],
    [
        "archkeel.analyzer.typescript.collect._Collection._local",
        'relative = specifier.startswith(("./", "../"))',
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._local",
        "declaration = path if path.endswith(_DECLARATION) else None",
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._local",
        "explicit = relative and specifier.endswith(_EXPLICIT_RUNTIME)",
    ],
    [
        "archkeel.analyzer.typescript.config.is_outside",
        'return PathToken.parse(rel) is PathToken.PARENT or rel.startswith("../")',
    ],
    ["archkeel.analyzer.typescript.config._extended", 'if not named.startswith(("./", "../")):'],
    [
        "archkeel.analyzer.typescript.config._extended",
        'if not snapshot.is_file(path) and not path.endswith(".json"):',
    ],
    [
        "archkeel.analyzer.typescript.config._base_path",
        'path: str = "/" + spec if not spec.startswith("/") else spec',
    ],
    ["archkeel.analyzer.typescript.config._discover", 'if spec.rstrip("/").endswith("**"):'],
    [
        "archkeel.analyzer.typescript.resolve.package_name",
        'return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]',
    ],
    [
        "archkeel.analyzer.typescript.resolve._typed_name",
        'if specifier.startswith("@") and len(parts) > 1:',
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.format_of",
        "if rel.endswith(_ESM_EXTENSIONS):",
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.format_of",
        "if rel.endswith(_CJS_EXTENSIONS):",
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.format_of",
        "if not rel.endswith(_SCOPE_FORMATS):",
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.resolve",
        'found = self._by_name(candidate, specifier.endswith("/"), esm, kinds, True)',
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.resolve",
        'if self._exports_aware and specifier.startswith("#"):',
    ],
]


def test_shared_source_input_port_exists():
    assert importlib.util.find_spec("archkeel.analyzer.typescript.source_input") is not None


def test_declaration_cts_keeps_written_commonjs_loader_semantics(tmp_path):
    import json

    from native_typescript import collect

    from archkeel.ir.facts import BuiltinTarget
    from archkeel.ir.protocol import (
        CollectionRequest,
        SnapshotInput,
        SourceScope,
        TypeScriptSettings,
    )

    (tmp_path / "src").mkdir()
    (tmp_path / "src/main.d.cts").write_text('const fs = require("node:fs");')
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"moduleResolution": "node"}, "files": ["src/main.d.cts"]})
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("src",), "app"),
            TypeScriptSettings("tsconfig.json"),
        )
    )
    assert any(isinstance(target, BuiltinTarget) for target in facts.imports)
    assert not any(
        "Unproven or shadowed require" in row.data.get("reason", "") for row in facts.coverage.gaps
    )
