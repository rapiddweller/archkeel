# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bundler mode: what a bundler decides is known behaviour, everything else stays UNKNOWN.

The mode is an explicit `[scan] bundler` claim (AD-260). Every case is also run without it, so a
regression of the default (compiler-faithful) behaviour shows up here as well.
"""

import json
from pathlib import Path

import pytest

from archkeel.analyzer.typescript.collect import collect
from archkeel.ir.facts import (
    ExternalPackageTarget,
    ImportTarget,
    LocalTarget,
    SourceFacts,
    UnresolvedTarget,
)
from archkeel.ir.facts_codec import decode_response, encode_response
from archkeel.ir.facts_validation import validate_source_facts
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

BUNDLER = {"module": "ESNext", "moduleResolution": "Bundler"}
NODENEXT = {"module": "NodeNext", "moduleResolution": "NodeNext"}
ASSET = "bundler:asset"
ALIAS_GAP = "Local alias runtime conditions are not proven"
REQUIRES = "Bundler mode requires moduleResolution bundler"
_EMPTY = "export {};\n"


def _facts(
    root: Path,
    files: dict[str, str],
    *,
    bundler: bool,
    options: dict[str, object] | None = None,
    paths: dict[str, list[str]] | None = None,
    roots: tuple[str, ...] = ("src",),
    include: tuple[str, ...] = ("src",),
) -> SourceFacts:
    compiler: dict[str, object] = {**(options or BUNDLER)}
    if paths is not None:
        compiler.update(baseUrl=".", paths=paths)
    tsconfig = {"compilerOptions": compiler, "include": list(include)}
    for rel, content in {"tsconfig.json": json.dumps(tsconfig), **files}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content)
    request = CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(roots, "app"),
        TypeScriptSettings(bundler=bundler),
    )
    facts = decode_response(encode_response(CollectionResponse(collect(request)))).facts
    validate_source_facts(facts)
    return facts


def _gaps(facts: SourceFacts) -> list[str]:
    return sorted(item.title for item in facts.coverage.gaps)


def _external(facts: SourceFacts) -> list[str]:
    return sorted(i.package for i in facts.imports if isinstance(i, ExternalPackageTarget))


def _kinds(facts: SourceFacts) -> list[type[ImportTarget]]:
    return [type(item) for item in facts.imports]


def _package(name: str, **fields: object) -> dict[str, str]:
    return {f"node_modules/{name}/package.json": json.dumps({"name": name, **fields})}


@pytest.mark.parametrize("bundler", [True, False])
def test_alias_to_a_scanned_file_is_proven_only_in_bundler_mode(tmp_path, bundler):
    files = {"src/main.ts": 'import x from "@/lib/x";\nexport const y = x;\n', "src/lib/x.ts": ""}
    facts = _facts(tmp_path, files, bundler=bundler, paths={"@/*": ["src/*"]})
    target = next(i for i in facts.imports if isinstance(i, LocalTarget))
    if bundler:
        assert target.runtime_file == "src/lib/x.ts"
        assert _gaps(facts) == []
    else:
        assert target.runtime_file is None
        assert any(ALIAS_GAP in gap for gap in _gaps(facts))


@pytest.mark.parametrize("bundler", [True, False])
def test_directory_package_keeps_its_gap(tmp_path, bundler):
    files = {
        "src/main.ts": 'import x from "./lib";\nexport const y = x;\n',
        "src/lib/package.json": json.dumps({"main": "./entry.ts"}),
        "src/lib/entry.ts": "export default 1;\n",
    }
    facts = _facts(tmp_path, files, bundler=bundler)
    assert "Local directory runtime metadata is not proven: ./lib" in _gaps(facts)


@pytest.mark.parametrize(
    "name,manifest",
    [
        ("rs", {"exports": {"react-server": "./s.js", "default": "./i.js"}}),
        ("ms", {"exports": {"module-sync": "./s.js", "default": "./i.js"}}),
        ("custom", {"exports": {"my-condition": "./s.js"}}),
        ("tv", {"typesVersions": {"*": {"*": ["t/*"]}}}),
    ],
)
@pytest.mark.parametrize("bundler", [True, False])
def test_unmodelled_package_metadata_is_an_external_edge(tmp_path, name, manifest, bundler):
    files = {
        "src/main.ts": f'import x from "{name}";\nexport const y = x;\n',
        **_package(name, **manifest),
    }
    facts = _facts(tmp_path, files, bundler=bundler)
    if bundler:
        assert _external(facts) == [name]
        assert _gaps(facts) == []
    else:
        assert _external(facts) == []
        assert _gaps(facts) != []


def test_type_only_import_of_a_typesversions_package_is_an_external_edge(tmp_path):
    files = {
        "src/main.ts": 'import type { T } from "tv";\nexport type U = T;\n',
        **_package("tv", typesVersions={"*": {"*": ["t/*"]}}),
    }
    facts = _facts(tmp_path, files, bundler=True)
    assert _external(facts) == ["tv"]
    assert _gaps(facts) == []


@pytest.mark.parametrize("bundler", [True, False])
def test_rejected_exports_shapes_stay_unknown(tmp_path, bundler):
    files = {
        "src/main.ts": 'import x from "pkg";\nexport const y = x;\n',
        **_package("pkg", exports=["./a.js"]),
    }
    facts = _facts(tmp_path, files, bundler=bundler)
    assert "Package exports shape is not observed: pkg" in _gaps(facts)
    assert _external(facts) == []


_ASSETS = [
    ('import "./a.css";', "src/a.css"),
    ('import s from "./a.module.css";', "src/a.module.css"),
    ('import u from "./a.webp?url";', "src/a.webp"),
    ('import w from "./a.wasm?url";', "src/a.wasm"),
]


@pytest.mark.parametrize("statement,asset", _ASSETS)
@pytest.mark.parametrize("bundler", [True, False])
def test_existing_assets_are_bundler_asset_edges(tmp_path, statement, asset, bundler):
    files = {"src/main.ts": statement + "\nexport {};\n", asset: ""}
    facts = _facts(tmp_path, files, bundler=bundler)
    if bundler:
        assert _external(facts) == [ASSET]
        assert _gaps(facts) == []
    else:
        assert _external(facts) == []
        assert any(gap.startswith("Unresolved module") for gap in _gaps(facts))


@pytest.mark.parametrize("statement,_asset", _ASSETS[:3])
def test_missing_assets_stay_unresolved(tmp_path, statement, _asset):
    facts = _facts(tmp_path, {"src/main.ts": statement + "\nexport {};\n"}, bundler=True)
    assert _external(facts) == []
    assert [gap.split(":")[0] for gap in _gaps(facts)] == ["Unresolved module"]


def test_uppercase_extension_is_not_an_asset(tmp_path):
    files = {"src/main.ts": 'import "./a.CSS";\nexport {};\n', "src/a.CSS": ""}
    facts = _facts(tmp_path, files, bundler=True)
    assert _external(facts) == []
    assert _gaps(facts) == ["Unresolved module: ./a.CSS"]


@pytest.mark.parametrize("bundler", [True, False])
def test_bare_package_asset_needs_the_installed_package(tmp_path, bundler):
    files = {
        "src/main.ts": 'import "leaflet/dist/leaflet.css";\nexport {};\n',
        **_package("leaflet"),
        "node_modules/leaflet/dist/leaflet.css": "",
    }
    facts = _facts(tmp_path, files, bundler=bundler)
    if bundler:
        assert _external(facts) == ["leaflet"]
        assert _gaps(facts) == []
    else:
        assert _external(facts) == []
        assert _gaps(facts) != []


def test_bare_package_asset_of_an_absent_package_stays_unresolved(tmp_path):
    files = {"src/main.ts": 'import "leaflet/dist/leaflet.css";\nexport {};\n'}
    facts = _facts(tmp_path, files, bundler=True)
    assert _external(facts) == []
    assert _gaps(facts) == ["Unresolved module: leaflet/dist/leaflet.css"]


@pytest.mark.parametrize("json_module", [True, False])
@pytest.mark.parametrize("bundler", [True, False])
def test_json_inside_the_roots_is_a_bundler_asset_edge(tmp_path, json_module, bundler):
    files = {
        "src/main.ts": 'import data from "./data.json";\nexport const d = data;\n',
        "src/data.json": "{}",
    }
    options = {**BUNDLER, "resolveJsonModule": json_module}
    facts = _facts(tmp_path, files, bundler=bundler, options=options)
    if bundler:
        assert _external(facts) == [ASSET]
        assert _gaps(facts) == []
        assert facts.coverage.full_scope
        assert not any(isinstance(i, UnresolvedTarget) for i in facts.imports)
    else:
        assert _external(facts) == []
        assert _gaps(facts) != []


@pytest.mark.parametrize("bundler", [True, False])
def test_workspace_alias_outside_the_roots_is_an_external_package(tmp_path, bundler):
    files = {
        "src/main.ts": 'import { c } from "@obc/api-client";\nexport const d = c;\n',
        "api/src/index.ts": "export const c = 1;\n",
    }
    facts = _facts(
        tmp_path, files, bundler=bundler, paths={"@obc/api-client": ["api/src/index.ts"]}
    )
    if bundler:
        assert _external(facts) == ["@obc/api-client"]
        assert _gaps(facts) == []
    else:
        assert _external(facts) == []
        assert "Local dependency outside selected source scope: api/src/index.ts" in _gaps(facts)


def test_non_package_alias_and_relative_outside_the_roots_keep_the_gap(tmp_path):
    files = {
        "src/main.ts": (
            'import a from "@/ext";\nimport b from "../outside";\nexport const d = [a, b];\n'
        ),
        "ext.ts": "export default 1;\n",
        "outside.ts": "export default 2;\n",
    }
    facts = _facts(tmp_path, files, bundler=True, paths={"@/ext": ["ext.ts"]})
    gaps = _gaps(facts)
    assert "Local dependency outside selected source scope: ext.ts" in gaps
    assert "Local dependency outside selected source scope: outside.ts" in gaps
    assert _external(facts) == []


@pytest.mark.parametrize("bundler", [True, False])
def test_bundler_needs_moduleresolution_bundler(tmp_path, bundler):
    files = {"src/main.ts": 'import x from "@/lib/x";\nexport const y = x;\n', "src/lib/x.ts": ""}
    facts = _facts(tmp_path, files, bundler=bundler, options=NODENEXT, paths={"@/*": ["src/*"]})
    gaps = _gaps(facts)
    assert any(ALIAS_GAP in gap for gap in gaps)
    assert gaps.count(REQUIRES) == (1 if bundler else 0)


def test_blocked_tsconfig_reports_only_its_own_gap(tmp_path):
    files = {
        "src/main.ts": 'import "./a.css";\nimport x from "pkg";\nexport {};\n',
        "src/a.css": "",
    }
    options = {**BUNDLER, "customConditions": ["x"]}
    on = _facts(tmp_path / "on", files, bundler=True, options=options)
    off = _facts(tmp_path / "off", files, bundler=False, options=options)
    assert _gaps(on) == _gaps(off)
    assert _external(on) == []
    assert REQUIRES not in _gaps(on)


def test_mixed_project_has_an_exact_gap_list(tmp_path):
    files = {
        "src/main.ts": (
            'import a from "@/lib/x";\nimport "./a.css";\nimport d from "./d.json";\n'
            'import p from "rs";\nimport q from "q";\nimport z from "./missing.css";\n'
            "export const all = [a, d, p, q, z];\n"
        ),
        "src/lib/x.ts": "export default 1;\n",
        "src/a.css": "",
        "src/d.json": "{}",
        **_package("rs", exports={"react-server": "./s.js"}),
        **_package("q", exports=["./x.js"]),
    }
    facts = _facts(tmp_path, files, bundler=True, paths={"@/*": ["src/*"]})
    assert _gaps(facts) == [
        "Package exports shape is not observed: q",
        "Unresolved module: ./missing.css",
    ]
    assert _external(facts) == [ASSET, ASSET, "rs"]
    assert LocalTarget in _kinds(facts)


def test_bundler_mode_is_visible_in_the_result(tmp_path):
    files = {"src/main.ts": _EMPTY}
    on = _facts(tmp_path / "on", files, bundler=True)
    off = _facts(tmp_path / "off", files, bundler=False)
    assert "bundler-mode-v1" in on.capabilities.resolution_features
    assert "bundler-mode-v1" not in off.capabilities.resolution_features
    wrong = _facts(tmp_path / "wrong", files, bundler=True, options=NODENEXT)
    assert "bundler-mode-v1" not in wrong.capabilities.resolution_features


def test_query_makes_any_existing_file_an_asset_and_a_missing_one_stays_unresolved(tmp_path):
    files = {
        "src/main.ts": 'import t from "./a.txt?raw";\nimport m from "./b.txt?raw";\nexport {};\n',
        "src/a.txt": "x",
    }
    facts = _facts(tmp_path, files, bundler=True)
    assert _external(facts) == [ASSET]
    assert _gaps(facts) == ["Unresolved module: ./b.txt?raw"]


def test_scoped_package_asset_needs_the_installed_package(tmp_path):
    files = {
        "src/main.ts": 'import "@fontsource/inter/index.css";\nexport {};\n',
        **_package("@fontsource/inter"),
        "node_modules/@fontsource/inter/index.css": "",
    }
    assert _external(_facts(tmp_path / "on", files, bundler=True)) == ["@fontsource/inter"]
    del files["node_modules/@fontsource/inter/package.json"]
    del files["node_modules/@fontsource/inter/index.css"]
    absent = _facts(tmp_path / "off", files, bundler=True)
    assert _external(absent) == []
    assert _gaps(absent) == ["Unresolved module: @fontsource/inter/index.css"]


def test_asset_symlinked_out_of_the_snapshot_is_never_an_asset_edge(tmp_path):
    outside = tmp_path / "outside.css"
    outside.write_text("")
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.css").symlink_to(outside)
    files = {"src/main.ts": 'import "./a.css";\nexport {};\n'}
    facts = _facts(root, files, bundler=True)
    assert _external(facts) == []
    assert _gaps(facts) != []


def test_asset_symlinked_inside_the_snapshot_is_an_asset_edge(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "real.css").write_text("")
    (tmp_path / "src" / "a.css").symlink_to(tmp_path / "src" / "real.css")
    facts = _facts(tmp_path, {"src/main.ts": 'import "./a.css";\nexport {};\n'}, bundler=True)
    assert _external(facts) == [ASSET]
    assert _gaps(facts) == []


def test_asset_beyond_the_snapshot_by_name_is_never_an_asset_edge(tmp_path):
    outside = tmp_path / "outside.css"
    outside.write_text("")
    root = tmp_path / "proj"
    files = {"src/main.ts": 'import "../../outside.css";\nexport {};\n'}
    facts = _facts(root, files, bundler=True)
    assert _external(facts) == []
    assert _gaps(facts) != []


def test_package_directory_symlinked_out_of_the_snapshot_is_not_installed(tmp_path):
    elsewhere = tmp_path / "elsewhere" / "leaflet"
    elsewhere.mkdir(parents=True)
    root = tmp_path / "proj"
    (root / "node_modules").mkdir(parents=True)
    (root / "node_modules" / "leaflet").symlink_to(elsewhere)
    files = {"src/main.ts": 'import "leaflet/dist/leaflet.css";\nexport {};\n'}
    facts = _facts(root, files, bundler=True)
    assert _external(facts) == []
    assert _gaps(facts) != []


def test_bundler_facts_are_accepted_by_the_host_evaluation(tmp_path):
    from archkeel.check.evaluation.evaluate import evaluate_source
    from archkeel.ir.codec import parse_contract

    files = {"src/main.ts": 'import "./a.css";\nexport {};\n', "src/a.css": ""}
    facts = _facts(tmp_path, files, bundler=True)
    assert "bundler-mode-v1" in facts.capabilities.resolution_features
    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    evaluate_source(facts, contract, roots=("src",), namespace="app")


def test_alias_to_an_existing_asset_is_a_bundler_asset_edge(tmp_path):
    files = {
        "src/main.ts": 'import s from "@/ui/t.module.css";\nexport const x = s;\n',
        "src/ui/t.module.css": "",
    }
    facts = _facts(tmp_path, files, bundler=True, paths={"@/*": ["src/*"]})
    assert _external(facts) == [ASSET]
    assert _gaps(facts) == []


@pytest.mark.parametrize("bundler", [True, False])
def test_alias_to_a_package_directory_keeps_its_gap(tmp_path, bundler):
    files = {
        "src/main.ts": 'import x from "@/lib";\nexport const y = x;\n',
        "src/lib/package.json": json.dumps({"main": "./x.ts"}),
        "src/lib/x.ts": "export default 1;\n",
    }
    facts = _facts(tmp_path, files, bundler=bundler, paths={"@/*": ["src/*"]})
    target = next(i for i in facts.imports if isinstance(i, LocalTarget))
    assert target.runtime_file is None
    assert [g for g in _gaps(facts) if "runtime" in g] == [
        "Local alias runtime conditions are not proven: @/lib"
    ]


def test_workspace_package_in_node_modules_keeps_its_gap(tmp_path):
    files = {
        "src/main.ts": 'import x from "ws";\nexport const y = x;\n',
        "pkgs/ws/package.json": json.dumps(
            {"name": "ws", "exports": {".": {"types": "./src/index.ts", "import": "./dist/i.js"}}}
        ),
        "pkgs/ws/src/index.ts": "export default 1;\n",
    }
    for rel, content in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(content)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ws").symlink_to(tmp_path / "pkgs" / "ws")
    facts = _facts(tmp_path, {}, bundler=True, roots=("src", "pkgs"), include=("src", "pkgs"))
    targets = [i for i in facts.imports if isinstance(i, LocalTarget)]
    assert all(t.runtime_file is None for t in targets)
    assert any("runtime" in gap for gap in _gaps(facts))


def test_base_url_only_resolution_is_not_a_bundler_alias(tmp_path):
    files = {"src/main.ts": 'import x from "src/lib/x";\nexport const y = x;\n', "src/lib/x.ts": ""}
    facts = _facts(tmp_path, files, bundler=True, paths={"@unused/*": ["nope/*"]})
    target = next(i for i in facts.imports if isinstance(i, LocalTarget))
    assert target.runtime_file is None
    assert any(ALIAS_GAP in gap for gap in _gaps(facts))


def test_base_url_module_outside_the_roots_is_not_a_package_edge(tmp_path):
    files = {
        "src/main.ts": 'import h from "tests/h";\nexport const y = h;\n',
        "tests/h.ts": "export default 1;\n",
    }
    facts = _facts(tmp_path, files, bundler=True, paths={"@unused/*": ["nope/*"]})
    assert _external(facts) == []
    assert "Local dependency outside selected source scope: tests/h.ts" in _gaps(facts)


@pytest.mark.parametrize("bundler", [True, False])
def test_query_on_a_source_file_is_not_an_asset(tmp_path, bundler):
    files = {"src/main.ts": 'import w from "./w.ts?worker";\nexport {};\n', "src/w.ts": _EMPTY}
    facts = _facts(tmp_path, files, bundler=bundler)
    assert _external(facts) == []
    assert _gaps(facts) == ["Unresolved module: ./w.ts?worker"]


def test_alias_to_an_asset_outside_paths_is_unresolved(tmp_path):
    files = {"src/main.ts": 'import "src/a.css";\nexport {};\n', "src/a.css": ""}
    facts = _facts(tmp_path, files, bundler=True, paths={"@/*": ["src/*"]})
    assert _external(facts) == []
    assert _gaps(facts) == ["Unresolved module: src/a.css"]


def test_bare_package_asset_needs_the_file(tmp_path):
    files = {
        "src/main.ts": 'import "leaflet/dist/typo.css";\nexport {};\n',
        **_package("leaflet"),
    }
    facts = _facts(tmp_path, files, bundler=True)
    assert _external(facts) == []
    assert _gaps(facts) == ["Unresolved module: leaflet/dist/typo.css"]
    files["node_modules/leaflet/dist/typo.css"] = ""
    assert _external(_facts(tmp_path, files, bundler=True)) == ["leaflet"]


def test_blocked_tsconfig_does_not_advertise_bundler_mode(tmp_path):
    options = {**BUNDLER, "customConditions": ["x"]}
    facts = _facts(tmp_path, {"src/main.ts": _EMPTY}, bundler=True, options=options)
    assert "bundler-mode-v1" not in facts.capabilities.resolution_features


@pytest.mark.parametrize(
    ("specifier", "files"),
    [
        ("foo/../../src/a.css", {"src/a.css": ""}),
        ("foo/../a.css", {"node_modules/a.css": ""}),
        ("foo/./a.css", {"node_modules/foo/a.css": ""}),
        ("foo/x/../a.css", {"node_modules/foo/a.css": ""}),
        ("@s/p/../x.css", {"node_modules/@s/x.css": ""}),
        ("@s/p/../../src/a.css", {"src/a.css": ""}),
        ("@s/p/../../../src/a.css", {"src/a.css": ""}),
    ],
)
def test_bare_package_asset_cannot_leave_the_package_directory(tmp_path, specifier, files):
    files = {
        "src/main.ts": f'import "{specifier}";\nexport {{}};\n',
        **_package("foo"),
        **_package("@s/p"),
        **files,
    }
    facts = _facts(tmp_path, files, bundler=True)
    assert _external(facts) == []
    assert _gaps(facts) == [f"Unresolved module: {specifier}"]


@pytest.mark.parametrize("bundler", [True, False])
@pytest.mark.parametrize(
    ("importer", "specifier"), [("src/main.ts", "."), ("src/sub/main.ts", "..")]
)
def test_dot_and_dotdot_resolve_like_index_in_bundler_mode(tmp_path, bundler, importer, specifier):
    files = {
        importer: f'import {{ x }} from "{specifier}";\nexport const y = x;\n',
        "src/index.ts": "export const x = 1;\n",
    }
    facts = _facts(tmp_path, files, bundler=bundler)
    target = next(i for i in facts.imports if isinstance(i, LocalTarget))
    if bundler:
        assert target.runtime_file == "src/index.ts"
        assert _gaps(facts) == []
    else:
        assert target.runtime_file is None
        assert _gaps(facts) == [f"{ALIAS_GAP}: {specifier}"]


@pytest.mark.parametrize("bundler", [True, False])
def test_dot_import_of_a_package_directory_keeps_its_gap(tmp_path, bundler):
    files = {
        "src/main.ts": 'import { x } from ".";\nexport const y = x;\n',
        "src/package.json": json.dumps({"main": "./x.ts"}),
        "src/x.ts": "export const x = 1;\n",
    }
    facts = _facts(tmp_path, files, bundler=bundler)
    target = next(i for i in facts.imports if isinstance(i, LocalTarget))
    assert target.runtime_file is None
    assert [g for g in _gaps(facts) if "runtime" in g] != []


def _evaluate_with_features(facts: SourceFacts, features: tuple[str, ...]) -> None:
    from dataclasses import replace

    from archkeel.check.evaluation.evaluate import evaluate_source
    from archkeel.ir.codec import parse_contract

    changed = replace(facts, capabilities=replace(facts.capabilities, resolution_features=features))
    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    evaluate_source(changed, contract, roots=("src",), namespace="app")


def test_evaluation_accepts_the_bundler_feature_beside_each_registered_set(tmp_path):
    plain = _facts(tmp_path / "plain", {"src/main.ts": _EMPTY}, bundler=False)
    on = _facts(tmp_path / "on", {"src/main.ts": _EMPTY}, bundler=True)
    features = on.capabilities.resolution_features
    assert "script-globals-v1" in features
    assert features == (*plain.capabilities.resolution_features, "bundler-mode-v1")
    _evaluate_with_features(plain, plain.capabilities.resolution_features)
    _evaluate_with_features(on, features)
    without_globals = tuple(f for f in features if f != "script-globals-v1")
    _evaluate_with_features(on, without_globals)


def test_evaluation_rejects_a_duplicated_bundler_feature(tmp_path):
    from archkeel.ir.facts_codec import ProtocolError

    on = _facts(tmp_path, {"src/main.ts": _EMPTY}, bundler=True)
    with pytest.raises(ProtocolError, match="duplicate resolution feature"):
        _evaluate_with_features(on, (*on.capabilities.resolution_features, "bundler-mode-v1"))


def test_evaluation_rejects_the_bundler_feature_without_a_registered_set(tmp_path):
    from archkeel.ir.facts_codec import ProtocolError

    on = _facts(tmp_path, {"src/main.ts": _EMPTY}, bundler=True)
    with pytest.raises(ProtocolError, match="not registered"):
        _evaluate_with_features(on, ("bundler-mode-v1",))
