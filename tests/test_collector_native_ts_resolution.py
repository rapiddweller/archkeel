# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1263: module resolution of TypeScript on small projects, by the rules of TypeScript.

Each project below holds one family of import forms (path mappings with fallbacks, `NodeNext`,
a bundler asset, JSX with `allowJs`, the forms of ES modules, package exports maps). The expected
edges follow from the TypeScript rules and from the files that exist, not from an earlier output of
a collector. A project that the collector resolves wrongly gives another edge set. The edge set is
exact: an import that resolves to a wrong file, or that does not resolve, fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from core_support import run

from archkeel.cli import core_only
from tools.fixture_tree import fixture_tree

SOURCES = Path(__file__).parent / "golden/typescript/sources"


def _edges(root: Path) -> tuple[str, set[tuple[str, str]], set[tuple[str, str]], list[str]]:
    """The status, the resolved file edges, the other edges and the gap reasons."""
    _, envelope = run("report", "--root", str(root), "--topology")
    frame = envelope["frame"]

    def name(module: str) -> str:
        return module.split(".src.", 1)[-1].replace("_x2e_", ".")

    resolved: set[tuple[str, str]] = set()
    other: set[tuple[str, str]] = set()
    for edge in frame["topology"]["edges"]:
        source, target = name(edge["source"]), edge["target"]
        if edge["resolution"] == "resolved":
            resolved.add((source, name(target)))
        else:
            other.add((source, f"{edge['resolution']}:{target}"))
    reasons = [gap["reason"] for gap in frame["collection_gaps"]]
    reasons += [gap["reason"] for gap in envelope.get("gaps", []) if "reason" in gap]
    return envelope["status"], resolved, other, reasons


# name -> (resolved edges, other edges that must appear, gap reasons that must appear)
CASES = {
    # `baseUrl: src`; `@lib/*` tries `lib/*` and then `shared/*`; `@only` is exact; `@none/*` is the
    # longest match for `@none/x`, so `*` is not tried; `*` maps `third`; `base/plain` falls back
    # to `baseUrl`; the relative import names the same file as `@lib/one`.
    "synthetic-paths-multi": (
        {
            ("main.ts", "lib.one.ts"),
            ("main.ts", "shared.two.ts"),
            ("main.ts", "lib.only.ts"),
            ("main.ts", "fallback.third.ts"),
            ("main.ts", "base.plain.ts"),
        },
        {("main.ts", "unresolved:@none/x")},
        ["Unresolved module: @none/x"],
    ),
    # NodeNext: `./lib.js` names `lib.ts`, `./legacy.cjs` names `legacy.cts`; a CommonJS file cannot
    # `require` the ES module `helper.mjs` at run time (the edge exists, the run time is unproven).
    "synthetic-nodenext": (
        {
            ("entry.mts", "lib.ts"),
            ("entry.mts", "legacy.cts"),
            ("legacy.cts", "helper.mts"),
            ("legacy.cts", "lib.ts"),
        },
        {("legacy.cts", "external:fs")},
        ["CommonJS runtime file is unavailable: ./helper.mjs"],
    ),
    # Bundler: an asset import is external to the scan; `@/*` maps to `src/*`; a missing target is
    # unresolved.
    "synthetic-bundler": (
        {("index.ts", "cart.ts")},
        {("index.ts", "external:bundler:asset"), ("index.ts", "unresolved:@/nowhere")},
        ["Unresolved module: @/nowhere"],
    ),
    # `@util/*` and `@app` map to files; `.tsx`, `.cts`, `export ... from`, `import type`,
    # `import()` and `require()` of a relative file name the same files; `react` is not installed.
    "synthetic-tsx-paths": (
        {
            ("app.greeting.tsx", "util.format.ts"),
            ("app.index.ts", "app.greeting.tsx"),
            ("app.index.ts", "util.format.ts"),
            ("legacy.cts", "util.format.ts"),
            ("main.ts", "app.index.ts"),
            ("main.ts", "util.format.ts"),
        },
        {("app.greeting.tsx", "unresolved:react"), ("main.ts", "external:fs")},
        [],
    ),
    # `allowJs` + JSX: an import without extension finds `.jsx`, `.tsx` and `.js`; a literal
    # `require` resolves; a computed `require` does not; a missing file is unresolved.
    "synthetic-allowjs": (
        {
            ("app.jsx", "panel.tsx"),
            ("app.jsx", "button.jsx"),
            ("panel.tsx", "button.jsx"),
            ("panel.tsx", "frame.tsx"),
            ("frame.tsx", "plain.js"),
            ("plain.js", "util.js"),
        },
        {("plain.js", "unresolved:./gone"), ("plain.js", "external:fs")},
        ["CommonJS runtime target is not proven: ./util"],
    ),
    # Each form of an ES module import, export and dynamic import names `lib`, `types`, `side` or
    # the declaration `shim.d.ts`; `node:fs` is external; a missing file is unresolved; a computed
    # specifier is held. (`export type *` and triple-slash references are held, not asserted.)
    "synthetic-esm-forms": (
        {
            ("imports.ts", "lib.ts"),
            ("imports.ts", "side.ts"),
            ("imports.ts", "types.ts"),
            ("imports.ts", "shim.d.ts"),
            ("dynamic.ts", "lib.ts"),
            ("dynamic.ts", "side.ts"),
            ("dynamic.ts", "types.ts"),
            ("reexports.ts", "lib.ts"),
            ("reexports.ts", "types.ts"),
        },
        {
            ("imports.ts", "external:node:fs"),
            ("dynamic.ts", "unresolved:./gone"),
            ("reexports.ts", "unresolved:./missing"),
        },
        [
            "Unresolved module: ./gone",
            "Unresolved module: ./missing",
            "Computed dynamic_import cannot be resolved",
        ],
    ),
    # Package maps: a package outside the scan is external; a path that `exports` does not list is
    # not reachable. The three forms in `HELD_OR_RIGHT` are held or resolved to the right file.
    "synthetic-package-maps": (
        set(),
        {
            ("index.ts", "external:exact"),
            ("index.ts", "external:plain"),
            ("index.ts", "unresolved:exact/hidden"),
        },
        ["Unresolved module: exact/hidden"],
    ),
    # A file that does not parse, a missing import and a computed write to a global are all held.
    "synthetic-gaps": (
        set(),
        {("module.ts", "unresolved:./not-there")},
        [
            "Unresolved module: ./not-there",
            "Syntax error in src/broken.ts",
            "Escaped or computed global host dependency",
        ],
    ),
    # A namespace that a script builds is used from another script; a member that no script
    # publishes is held.
    "synthetic-script-namespace": (
        {("use.js", "shapes.js")},
        set(),
        ["Shapes.absent"],
    ),
}

# Forms that the collector may hold or resolve: the outcome is a gap that names the specifier or
# the right target, never another file.
HELD_OR_RIGHT = {
    "synthetic-package-maps": {
        "#internal": {("index.ts", "internal.ts")},
        "patterned/features/one": set(),
        "synth-maps": {("index.ts", "index.ts")},
    }
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_native_collector_resolves_the_imports_as_typescript_does(
    name: str, release_core: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    with fixture_tree(SOURCES / name) as root:
        status, resolved, other, reasons = _edges(root)
    want_resolved, want_other, want_reasons = CASES[name]
    # Every project holds something on purpose (a gap, an unresolved import): never PASS.
    assert status == "UNKNOWN"
    right = HELD_OR_RIGHT.get(name, {})
    assert resolved - set().union(*right.values()) == want_resolved
    assert want_other <= other, sorted(want_other - other)
    for reason in want_reasons:
        assert any(reason in found for found in reasons), reason
    for specifier, edges in right.items():
        package = specifier.split("/")[0]
        held = any(specifier in found for found in reasons)
        assert held or edges <= resolved or any(package in target for _, target in other), specifier
