# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""What the in-package TypeScript collector proves, and everything it leaves UNKNOWN.

Each test is a behaviour of the Node reference collector's acceptance suite, asserted here
without Node: the frontend may be more conservative than the reference, never less.
"""

import hashlib
import json
import os
from pathlib import Path

import pytest

from archkeel.analyzer.typescript.collect import collect
from archkeel.ir.facts import (
    BuiltinTarget,
    ExternalPackageTarget,
    LocalTarget,
    SourceFacts,
    UnresolvedTarget,
)
from archkeel.ir.facts_codec import decode_response, encode_response
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
NODENEXT = {"module": "NodeNext", "moduleResolution": "NodeNext"}
NODE10 = {"module": "CommonJS", "moduleResolution": "Node"}


def _facts(
    root: Path,
    files: dict[str, str | bytes],
    config: dict[str, object] | None = None,
    roots: tuple[str, ...] = ("src",),
    options: dict[str, object] | None = None,
) -> SourceFacts:
    tsconfig = {"compilerOptions": options or NODENEXT, "include": ["src"], **(config or {})}
    for rel, content in {"tsconfig.json": json.dumps(tsconfig), **files}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(content if isinstance(content, bytes) else content.encode())
    request = CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False), SourceScope(roots, "app"), TypeScriptSettings()
    )
    # Whatever the collector builds must survive the strict Core decoder.
    return decode_response(encode_response(CollectionResponse(collect(request)))).facts


def _manifest(name: str, **fields: object) -> str:
    return json.dumps({"name": name, "version": "1.0.0", **fields})


def _only(*paths: str) -> dict[str, object]:
    return {"files": list(paths), "include": []}


@pytest.mark.parametrize("allow_js", [None, False, True])
def test_check_js_includes_javascript_unless_allow_js_is_explicitly_false(
    tmp_path: Path, allow_js: bool | None
) -> None:
    options = {**NODE10, "checkJs": True}
    if allow_js is not None:
        options["allowJs"] = allow_js
    facts = _facts(
        tmp_path,
        {"src/main.ts": "export {};", "src/hidden.js": "require('./missing.cjs');"},
        options=options,
    )
    assert ("src/hidden.js" in facts.coverage.selected_files) == (allow_js is not False)
    if allow_js is not False:
        assert not facts.coverage.full_scope
        assert any(isinstance(target, UnresolvedTarget) for target in facts.imports)


def _gaps(facts: SourceFacts) -> list[str]:
    return [item.title for item in facts.coverage.gaps]


def _targets(facts: SourceFacts) -> dict[str, object]:
    by_id = {item.import_id: item for item in facts.imports}
    result = {}
    for section in facts.sections:
        for record in section.records if section.name == "imports" else ():
            result[f"{record.kind}:{record.data.get('specifier')}"] = by_id[record.id]
    return result


def _files(facts: SourceFacts) -> list[str]:
    return [item.rel_path for item in facts.files]


@pytest.mark.parametrize(
    "options", [{"allowJs": "true"}, {"resolveJsonModule": "true"}, {"baseUrl": 42}, "invalid"]
)
def test_invalid_configuration_cannot_prove_import_targets(tmp_path: Path, options: object) -> None:
    facts = _facts(
        tmp_path,
        {"src/main.ts": "import './value.js';", "src/value.ts": "export {};"},
        config={"compilerOptions": options},
    )
    assert not facts.coverage.full_scope
    assert facts.imports
    assert all(isinstance(target, UnresolvedTarget) for target in facts.imports)
    assert any("Compiler option" in gap for gap in _gaps(facts))


def test_forms_resolve_through_aliases_and_the_commonjs_runtime_closure(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path,
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
        {"compilerOptions": {**NODENEXT, "baseUrl": ".", "paths": {"@app/*": ["src/*"]}}},
    )
    assert facts.coverage.full_scope, _gaps(facts)
    assert facts.profile == "archkeel-typescript-imports"
    assert _files(facts) == [
        "src/extra.ts",
        "src/host.cjs",
        "src/host.d.cts",
        "src/main.ts",
        "src/value.ts",
    ]
    imports = [item for item in facts.imports if isinstance(item, BuiltinTarget)]
    assert [item.name for item in imports] == ["node:os"]
    host = [
        item for item in facts.imports if isinstance(item, LocalTarget) and item.declaration_file
    ]
    assert {(item.runtime_file, item.declaration_file) for item in host} == {
        ("src/host.cjs", "src/host.d.cts")
    }
    records = [r for s in facts.sections for r in s.records if s.name == "imports"]
    assert {r.kind for r in records} == {
        "import",
        "reexport",
        "import_type",
        "dynamic_import",
        "import_equals",
        "require",
    }
    for record in records:
        assert record.data.get("relative_level") == 0
        assert record.data.get("under_type_checking") == record.data.get("type_only")


def test_a_second_run_is_byte_identical(tmp_path: Path) -> None:
    files = {"src/main.ts": "import './a.js'; import 'fs';", "src/a.ts": "export {};"}
    first = _facts(tmp_path, files)
    assert encode_response(CollectionResponse(first)) == encode_response(
        CollectionResponse(_facts(tmp_path, files))
    )


def test_selected_scope_is_distinct_from_resolution_only_inputs(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": "import '../shared/value.js';\n",
            "shared/value.ts": "export const value = 1;\n",
            "test/other.ts": "import 'missing';\n",
        },
        {"include": ["src", "test"]},
    )
    assert not facts.coverage.full_scope
    assert not any(item.rel_path.startswith(("test/", "shared/")) for item in facts.files)
    roles = {item.path: item.role for item in facts.inputs}
    assert roles["shared/value.ts"] == "resolution"
    assert roles["src/main.ts"] == "selected"
    assert "Local dependency outside selected source scope: shared/value.ts" in _gaps(facts)


def test_computed_shadowed_and_unresolved_imports_leave_explicit_gaps(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": (
                "require(variable);\nfunction f(require: Function) { require('./missing.js'); }\n"
                "import './not-here.js';\nimport(name);\n"
            )
        },
    )
    assert not facts.coverage.full_scope
    gaps = _gaps(facts)
    assert "Computed dynamic_import cannot be resolved" in gaps
    assert "Unproven or shadowed require call" in gaps
    assert "Unresolved module: ./not-here.js" in gaps
    assert any(isinstance(item, UnresolvedTarget) for item in facts.imports)


def test_syntax_and_config_errors_cannot_claim_complete_coverage(tmp_path: Path) -> None:
    facts = _facts(tmp_path, {"src/main.ts": "const = ;\n"})
    assert any(item.startswith("Syntax error in src/main.ts") for item in _gaps(facts))
    broken = tmp_path / "broken"
    config = _facts(broken, {"src/main.ts": "export {};"}, {"extends": "../absent.json"})
    assert not config.coverage.full_scope
    assert len(config.coverage.gaps) >= 1


def test_declarations_do_not_substitute_for_missing_runtime_implementations(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": "import host = require('./host.cjs');",
            "src/host.d.cts": "declare const host: string; export = host;",
        },
    )
    assert any(item.startswith("Runtime implementation unavailable") for item in _gaps(facts))
    (target,) = [item for item in facts.imports if isinstance(item, LocalTarget)]
    assert (target.declaration_file, target.runtime_file) == ("src/host.d.cts", None)


def test_type_only_named_imports_invent_no_declaration_runtime_requirement(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": (
                "import { type Value } from './value.js'; export { type Value } from './value.js';"
            ),
            "src/value.d.ts": "export interface Value { value: string }",
        },
    )
    assert facts.coverage.full_scope, _gaps(facts)
    records = [r for s in facts.sections for r in s.records if s.name == "imports"]
    assert all(r.data.get("type_only") is True for r in records)


def test_esm_require_indirect_require_and_triple_slash_references_are_unknown(
    tmp_path: Path,
) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.mts": (
                "/// <reference path='./other.d.ts' />\n"
                "const load = require; require('node:fs'); load(name);"
            ),
            "src/other.d.ts": "export {};",
        },
    )
    gaps = _gaps(facts)
    assert not facts.coverage.full_scope
    assert any("Indirect require" in item for item in gaps)
    assert "Unproven or shadowed require call" in gaps
    assert "Unobserved triple-slash reference: ./other.d.ts" in gaps
    assert facts.imports == ()


def test_a_resolved_external_package_is_bound_to_its_snapshot_inputs(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": "import 'example';",
            "node_modules/example/package.json": _manifest("example", types="index.d.ts"),
            "node_modules/example/index.d.ts": "export {};",
        },
    )
    assert facts.coverage.full_scope, _gaps(facts)
    assert [item.package for item in facts.imports if isinstance(item, ExternalPackageTarget)] == [
        "example"
    ]
    paths = {item.path: item.role for item in facts.inputs}
    assert paths["node_modules/example/package.json"] == "resolution"
    assert paths["node_modules/example/index.d.ts"] == "resolution"


def test_a_package_that_is_not_installed_is_unresolved_never_external(tmp_path: Path) -> None:
    facts = _facts(tmp_path, {"src/main.ts": "import 'absent';"})
    assert not facts.coverage.full_scope
    (target,) = facts.imports
    assert isinstance(target, UnresolvedTarget)
    assert "Unresolved module: absent" in _gaps(facts)


def test_the_local_javascript_closure_is_parsed_and_never_executed(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": "import './runtime.js';",
            "src/runtime.js": "throw new Error('must not execute'); import './leaf.js';",
            "src/leaf.js": "import 'node:fs';",
        },
    )
    assert facts.coverage.full_scope, _gaps(facts)
    assert "src/leaf.js" in _files(facts)
    assert any(isinstance(item, BuiltinTarget) for item in facts.imports)


@pytest.mark.parametrize(("runtime", "source"), [("js", "ts"), ("mjs", "mts"), ("cjs", "cts")])
def test_explicit_runtime_javascript_survives_source_substitution_and_changes_the_digest(
    tmp_path: Path, runtime: str, source: str
) -> None:
    files = {
        "package.json": '{"type":"module"}',
        "src/main.mts": f"import './leaf.{runtime}';",
        f"src/leaf.{source}": "export const value = 1;",
        f"src/leaf.{runtime}": "throw new Error('must not execute'); import('./missing.js');",
    }
    options = {**NODENEXT, "noEmit": True}
    first = _facts(tmp_path, files, _only("src/main.mts"), options=options)
    assert not first.coverage.full_scope
    assert f"src/leaf.{runtime}" in _files(first)
    selected = {item.path for item in first.inputs if item.role == "selected"}
    # The compiler's source file is read too, but the runtime file is what Node would load.
    assert {"src/main.mts", f"src/leaf.{runtime}"} <= selected
    (target,) = [item for item in first.imports if isinstance(item, LocalTarget)]
    assert (target.file, target.runtime_file) == (f"src/leaf.{runtime}", f"src/leaf.{runtime}")
    assert any(
        isinstance(item, UnresolvedTarget) and item.specifier == "./missing.js"
        for item in first.imports
    )
    (tmp_path / f"src/leaf.{runtime}").write_text(
        "throw new Error('must not execute'); import('node:fs');"
    )
    second = _facts(tmp_path, {}, _only("src/main.mts"), options=options)
    assert second.coverage.full_scope, _gaps(second)
    assert second.source.source_digest != first.source.source_digest


def test_type_only_node_aliases_use_the_compiler_closure_while_value_imports_stay_builtin(
    tmp_path: Path,
) -> None:
    options = {"module": "ESNext", "moduleResolution": "Bundler"}
    config = {
        **_only("src/main.ts"),
        "compilerOptions": {**options, "baseUrl": ".", "paths": {"node:fs": ["src/local.ts"]}},
    }
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": "import type { Value } from 'node:fs'; import 'node:fs';",
            "src/local.ts": "import './missing.js'; export type Value = string;",
        },
        config,
    )
    assert not facts.coverage.full_scope
    kinds = [
        (type(item).__name__, getattr(item, "file", None) or getattr(item, "name", None))
        for item in facts.imports
    ]
    assert ("LocalTarget", "src/local.ts") in kinds
    assert ("BuiltinTarget", "node:fs") in kinds
    assert "src/local.ts" in _files(facts)


def test_bare_builtin_names_respect_a_local_type_alias(tmp_path: Path) -> None:
    config = {
        **_only("src/main.ts"),
        "compilerOptions": {
            "module": "ESNext",
            "moduleResolution": "Bundler",
            "baseUrl": ".",
            "paths": {"fs": ["src/local.ts"]},
        },
    }
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": "import type { Value } from 'fs'; import 'node:fs';",
            "src/local.ts": "export type Value = string;",
        },
        config,
    )
    assert facts.coverage.full_scope, _gaps(facts)
    assert any(
        isinstance(item, LocalTarget) and item.file == "src/local.ts" for item in facts.imports
    )
    assert any(isinstance(item, BuiltinTarget) and item.name == "node:fs" for item in facts.imports)


def test_project_references_and_a_missing_tsconfig_never_look_complete(tmp_path: Path) -> None:
    referenced = _facts(
        tmp_path, {"src/main.ts": "export {};"}, {"references": [{"path": "../generated"}]}
    )
    assert not referenced.coverage.full_scope
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("src",), "app"),
        TypeScriptSettings("missing.json"),
    )
    assert not collect(request).coverage.full_scope


def test_a_local_require_declaration_and_computed_commonjs_access_cannot_prove_imports(
    tmp_path: Path,
) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": (
                "function require(name: string) { return name; } require('./leaf.js'); "
                "module['require']('./leaf.js');"
            ),
            "src/leaf.ts": "export {};",
        },
    )
    assert not facts.coverage.full_scope
    assert facts.imports == ()
    assert "Computed require member use" in _gaps(facts)


@pytest.mark.parametrize(
    "source",
    [
        "module.require.call(module, './hidden.cjs');",
        "const load = module.require; load('./hidden.cjs');",
        "const load = module.require; load.call(module, './hidden.cjs');",
        "module['require'].apply(module, ['./hidden.cjs']);",
    ],
)
def test_indirect_module_require_cannot_claim_complete_dependency_coverage(
    tmp_path: Path, source: str
) -> None:
    facts = _facts(tmp_path, {"src/main.ts": source, "src/hidden.cjs": "module.exports = 7;"})
    observed = any(
        r.data.get("specifier") == "./hidden.cjs"
        for s in facts.sections
        for r in s.records
        if s.name == "imports"
    )
    assert observed or (not facts.coverage.full_scope and facts.coverage.gaps)
    control = _facts(
        tmp_path / "control",
        {"src/main.ts": "require('./hidden.cjs');", "src/hidden.cjs": "module.exports = 7;"},
    )
    assert control.coverage.full_scope
    assert "require:./hidden.cjs" in _targets(control)


@pytest.mark.parametrize(
    "source",
    [
        "import * as mod from 'node:module'; const load = mod.createRequire(import.meta.url);",
        "const { createRequire: factory } = require('node:module'); "
        "const load = factory(__filename);",
        "const factory = require('node:module').createRequire; const load = factory(__filename);",
        "import { createRequire as factory } from 'node:module'; factory(import.meta.url);",
        "import * as mod from 'node:module'; const load = mod['createRequire'](import.meta.url);",
        "import * as mod from 'node:module'; const load = mod[key](import.meta.url);",
    ],
)
def test_node_module_loader_factories_are_unknown(tmp_path: Path, source: str) -> None:
    facts = _facts(tmp_path, {"src/main.ts": source})
    assert not facts.coverage.full_scope
    assert "Node module loader is not observed" in _gaps(facts)
    assert len([item for item in _gaps(facts) if item == "Node module loader is not observed"]) == 1


def test_an_ordinary_function_named_create_require_is_not_a_loader(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path,
        {"src/main.ts": "function createRequire(x: string) { return x; } createRequire('data');"},
    )
    assert "Node module loader is not observed" in _gaps(facts)


def test_compiler_option_diagnostics_become_coverage_gaps(tmp_path: Path) -> None:
    invalid = _facts(
        tmp_path,
        {"src/main.ts": "export {};"},
        options={"module": "CommonJS", "moduleResolution": "NodeNext"},
    )
    assert not invalid.coverage.full_scope
    assert any("5110" in item for item in _gaps(invalid))
    valid = _facts(
        tmp_path / "ok",
        {"src/main.ts": "export {};"},
        options={**NODENEXT, "lib": ["ES2022"], "types": []},
    )
    assert valid.coverage.full_scope


@pytest.mark.parametrize(
    "comment",
    [
        '/** @typedef {import("./hidden.js").Value} Value */',
        '/** @import {Value} from "./hidden.js" */',
    ],
)
def test_jsdoc_imports_are_a_gap_not_a_guess(tmp_path: Path, comment: str) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.js": comment + "\nexport const x = 1;",
            "src/hidden.js": "export const Value = 1;",
        },
        _only("src/main.js"),
        options={**NODENEXT, "allowJs": True, "checkJs": True},
    )
    assert not facts.coverage.full_scope
    assert "JSDoc import is not observed" in _gaps(facts)
    assert "src/hidden.js" not in _files(facts)


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need privileges on Windows")
class TestSymbolicLinks:
    def test_workspace_subpath_ignores_the_root_types_entry(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules/example").symlink_to("../src/example")
        facts = _facts(
            tmp_path,
            {
                "src/main.ts": "import type { Value } from 'example/sub';",
                "src/example/package.json": '{"name":"example","types":"types.d.ts"}',
                "src/example/sub/types.d.ts": "export interface Wrong {}",
                "src/example/sub/index.ts": "export interface Value {}",
            },
            _only("src/main.ts"),
            options=NODE10,
        )
        target = _targets(facts)["import:example/sub"]
        assert isinstance(target, LocalTarget)
        assert target.file == "src/example/sub/index.ts"
        assert facts.coverage.full_scope, _gaps(facts)

    def test_a_resolver_symlink_outside_the_snapshot_stays_unknown_and_undigested(
        self, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside/src"
        outside.mkdir(parents=True)
        (outside / "private.ts").write_text("export const privateValue = 1;")
        root = tmp_path / "root"
        (root / "src").mkdir(parents=True)
        (root / "src/main.ts").write_text("import './private.js';")
        (root / "src/private.ts").symlink_to(outside / "private.ts")
        facts = _facts(root, {})
        assert not facts.coverage.full_scope
        assert "Resolver symlink outside snapshot" in _gaps(facts)
        assert all(item.path != "src/private.ts" for item in facts.inputs)

    def test_an_external_package_symlinked_outside_the_snapshot_is_incomplete(
        self, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside/pkg"
        outside.mkdir(parents=True)
        (outside / "package.json").write_text(
            '{"name":"example","version":"1.0.0","types":"index.d.ts"}'
        )
        (outside / "index.d.ts").write_text("export {};")
        root = tmp_path / "root"
        (root / "src").mkdir(parents=True)
        (root / "node_modules").mkdir()
        (root / "src/main.ts").write_text("import 'example';")
        (root / "node_modules/example").symlink_to(outside)
        facts = _facts(root, {})
        assert not facts.coverage.full_scope
        assert any(isinstance(item, UnresolvedTarget) for item in facts.imports)
        assert not any(item.path.startswith("node_modules/") for item in facts.inputs)

    def test_a_workspace_symlink_inside_the_selection_stays_local(self, tmp_path: Path) -> None:
        files = {
            "src/main.ts": "import 'example';",
            "src/shared/package.json": '{"name":"example","version":"1.0.0","types":"index.ts"}',
            "src/shared/index.ts": "import './hidden.js';",
            "src/shared/hidden.ts": "import './missing.js';",
        }
        (tmp_path / "node_modules").mkdir()
        facts = _facts(tmp_path, files, _only("src/main.ts"), options=NODENEXT)
        (tmp_path / "node_modules/example").symlink_to("../src/shared")
        facts = _facts(tmp_path, {}, _only("src/main.ts"))
        assert not facts.coverage.full_scope
        assert any(
            isinstance(item, LocalTarget) and item.file == "src/shared/index.ts"
            for item in facts.imports
        )
        assert not any(isinstance(item, ExternalPackageTarget) for item in facts.imports)
        assert {"src/shared/index.ts", "src/shared/hidden.ts"} <= set(_files(facts))
        (tmp_path / "src/shared/hidden.ts").write_text("export const value = 1;")
        value = _facts(tmp_path, {}, _only("src/main.ts"))
        assert "Local alias runtime conditions are not proven: example" in _gaps(value)
        target = _targets(value)["import:example"]
        assert isinstance(target, LocalTarget)
        assert target.runtime_file is None
        (tmp_path / "src/main.ts").write_text("import type {} from 'example';")
        assert _facts(tmp_path, {}, _only("src/main.ts")).coverage.full_scope

    def test_a_symlink_that_would_change_the_lookup_context_is_refused(
        self, tmp_path: Path
    ) -> None:
        files = {"src/main.ts": "import 'example';", "src/shared/index.ts": "export {};"}
        (tmp_path / "node_modules").mkdir()
        _facts(tmp_path, files)
        (tmp_path / "node_modules/example").symlink_to("../src/shared")
        options = {**NODENEXT, "preserveSymlinks": True}
        facts = _facts(tmp_path, {}, _only("src/main.ts"), options=options)
        assert not facts.coverage.full_scope
        assert any("preserveSymlinks" in item for item in _gaps(facts))
        assert _files(facts) == ["src/main.ts"]


def test_explicit_file_roots_keep_their_runtime_and_declaration_closure_and_literal_scope(
    tmp_path: Path,
) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": "import hosts = require('../supportedHosts.cjs');",
            "supportedHosts.cjs": "module.exports = [require('node:os').platform()];",
            "supportedHosts.d.cts": "declare const hosts: readonly string[]; export = hosts;",
            "unselected.ts": "import './missing.js';",
        },
        roots=("src", "supportedHosts.cjs", "supportedHosts.d.cts"),
    )
    assert facts.coverage.full_scope, _gaps(facts)
    assert facts.source.scope == ("src/**", "supportedHosts.cjs", "supportedHosts.d.cts")
    assert _files(facts) == ["src/main.ts", "supportedHosts.cjs", "supportedHosts.d.cts"]


@pytest.mark.parametrize("roots", [("src",), (".",)])
def test_repository_wide_scope_keeps_installed_dependencies_external(
    tmp_path: Path, roots: tuple[str, ...]
) -> None:
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": (
                "import type { Thing } from 'lib'; import { value } from 'lib'; "
                "export const use: Thing = value;"
            ),
            "node_modules/lib/package.json": _manifest("lib", types="index.d.ts", main="index.js"),
            "node_modules/lib/index.d.ts": (
                "export interface Thing { n: number }; export declare const value: Thing;"
            ),
            "node_modules/lib/index.js": "exports.value = { n: 1 };",
        },
        {"include": ["src/**/*.ts"], "exclude": ["node_modules"]},
        roots=roots,
    )
    assert facts.coverage.full_scope, _gaps(facts)
    assert _files(facts) == ["src/main.ts"]
    assert [item.package for item in facts.imports if isinstance(item, ExternalPackageTarget)] == [
        "lib",
        "lib",
    ]
    assert {item.path: item.role for item in facts.inputs}[
        "node_modules/lib/index.d.ts"
    ] == "resolution"


def test_an_unreferenced_explicit_file_root_is_selected_beyond_include_and_exclude(
    tmp_path: Path,
) -> None:
    files = {
        "src/main.ts": "export {};",
        "standalone.cjs": "require('./missing.cjs');",
        "standalone.ts": "export const value = 1;",
    }
    config = {"include": ["src"], "exclude": ["standalone.*"]}
    positive = _facts(tmp_path, files, config, roots=("standalone.ts",))
    assert positive.coverage.full_scope, _gaps(positive)
    assert _files(positive) == ["standalone.ts"]
    missing = _facts(tmp_path, {}, config, roots=("src", "standalone.cjs"), options=NODENEXT)
    assert not missing.coverage.full_scope
    assert _files(missing) == ["src/main.ts", "standalone.cjs"]


def test_tsconfig_cannot_select_installed_declarations_as_local_graph_files(tmp_path: Path) -> None:
    files = {
        "src/main.ts": "import type { Value } from 'example';",
        "node_modules/example/package.json": _manifest("example", types="index.d.ts"),
        "node_modules/example/index.d.ts": "export interface Value { value: string };",
    }
    config = {"include": ["src", "node_modules/example/**/*.ts"], "exclude": []}
    facts = _facts(tmp_path, files, config, roots=(".",))
    assert facts.coverage.full_scope, _gaps(facts)
    assert facts.coverage.selected_files == ("src/main.ts",)
    explicit = _facts(tmp_path, {}, config, roots=("src", "node_modules/example/index.d.ts"))
    assert not explicit.coverage.full_scope
    assert "Installed dependency cannot be a selected source root" in _gaps(explicit)


def test_external_runtime_api_identity_stays_distinct_from_its_declaration_provider(
    tmp_path: Path,
) -> None:
    files = {
        "package.json": '{"name":"app","imports":{"#local":"./src/local.ts"}}',
        "src/main.ts": (
            "import type { Uri } from 'vscode'; "
            "import type { Feature } from '@vendor/host/feature';"
        ),
        "node_modules/@types/vscode/package.json": _manifest("@types/vscode", types="index.d.ts"),
        "node_modules/@types/vscode/index.d.ts": "export interface Uri { path: string };",
        "node_modules/@types/vendor__host/package.json": _manifest(
            "@types/vendor__host", types="index.d.ts"
        ),
        "node_modules/@types/vendor__host/feature.d.ts": (
            "export interface Feature { name: string };"
        ),
    }
    facts = _facts(tmp_path, files)
    assert facts.coverage.full_scope, _gaps(facts)
    assert [item.package for item in facts.imports if isinstance(item, ExternalPackageTarget)] == [
        "vscode",
        "@vendor/host",
    ]
    records = {
        r.data.get("specifier"): r for s in facts.sections for r in s.records if s.name == "imports"
    }
    for specifier, runtime in (("vscode", "vscode"), ("@vendor/host/feature", "@vendor/host")):
        assert records[specifier].data.get("target_module") == runtime
        assert records[specifier].data.get("target_package") == runtime


def test_package_imports_are_unknown_never_an_external_package(tmp_path: Path) -> None:
    files = {
        "package.json": '{"name":"app","imports":{"#host":"host-api"}}',
        "src/main.ts": "import { value } from '#host';",
        "node_modules/host-api/package.json": _manifest("host-api", main="index.js"),
        "node_modules/host-api/index.js": "exports.value = 1;",
    }
    facts = _facts(tmp_path, files)
    assert not facts.coverage.full_scope
    (target,) = facts.imports
    assert isinstance(target, UnresolvedTarget)
    assert not any(isinstance(item, ExternalPackageTarget) for item in facts.imports)


def test_resolution_input_and_source_digests_bind_exact_source_bytes(tmp_path: Path) -> None:
    files: list[bytes] = [
        b"// marker \xff\nimport './value.js';\n",
        b"// marker \xfe\nimport './value.js';\n",
        "// marker café\nimport './value.js';\n".encode(),
    ]
    runs = []
    for index, data in enumerate(files):
        facts = _facts(
            tmp_path / str(index),
            {"src/main.ts": data, "src/value.ts": "export const value = 1;\n"},
        )
        assert facts.coverage.full_scope, _gaps(facts)
        assert _files(facts) == ["src/main.ts", "src/value.ts"]
        assert {item.path: item.digest for item in facts.inputs}["src/main.ts"] == hashlib.sha256(
            data
        ).hexdigest()
        runs.append(facts.source.source_digest)
    assert len(set(runs)) == 3
    # The same decoded text, different bytes: the digest must still differ.
    assert files[0].decode("utf-8", "replace") == files[1].decode("utf-8", "replace")


def test_blank_and_module_identity_facts(tmp_path: Path) -> None:
    facts = _facts(tmp_path, {"src/empty.ts": "﻿ \n", "src/a-b.ts": "export {};"})
    by_path = {item.rel_path: item for item in facts.files}
    assert by_path["src/empty.ts"].blank is True
    assert by_path["src/a-b.ts"].blank is False
    assert by_path["src/a-b.ts"].module == "app.src.a_x2d_b_x2e_ts"
    assert by_path["src/a-b.ts"].package == "app.src"


def _catalog(name: str) -> list[dict[str, object]]:
    return json.loads((FIXTURES / name).read_text())


def _hidden_case(root: Path, example: dict[str, object]) -> SourceFacts:
    files: dict[str, str | bytes] = {
        "package.json": json.dumps(example.get("manifest") or {}),
        "src/main.ts": str(example["source"]),
        "src/main.js": "require('./hidden.cjs');",
        "src/hidden.cjs": "require('./main.js');",
        **{str(k): str(v) for k, v in dict(example.get("files") or {}).items()},  # type: ignore[call-overload]
    }
    return _facts(root, files, _only("src/main.ts"))


@pytest.mark.parametrize(
    "example", _catalog("typescript-hidden-loaders.json"), ids=lambda item: str(item["name"])
)
def test_no_hidden_loader_pattern_claims_complete_coverage_the_catalog_denies(
    tmp_path: Path, example: dict[str, object]
) -> None:
    facts = _hidden_case(tmp_path, example)
    if not example["complete"]:
        assert not facts.coverage.full_scope
        assert facts.coverage.gaps
    # A direct literal require, or a plain import, still reaches the hidden cycle.
    if example.get("cycle"):
        assert len([item for item in facts.imports if isinstance(item, LocalTarget)]) == 3


def _runtime_example(root: Path, example: dict[str, object]) -> SourceFacts:
    default = {
        "src/runtime.ts": "export const value=1;",
        "src/runtime.js": "throw Error('must not execute');",
    }
    files = {
        "package.json": json.dumps(example["manifest"]),
        str(example.get("entry_path", "src/main.ts")): str(
            example.get("source") or f"import '{example['specifier']}';"
        ),
        **{str(k): str(v) for k, v in dict(example.get("files") or default).items()},  # type: ignore[call-overload]
    }
    selected = [str(item) for item in example.get("selected_files", ["src/main.ts"])]  # type: ignore[attr-defined]
    return _facts(root, files, _only(*selected))


@pytest.mark.parametrize(
    "example", _catalog("typescript-runtime-aliases.json"), ids=lambda item: str(item["name"])
)
def test_runtime_alias_catalog_never_claims_a_runtime_file_the_catalog_denies(
    tmp_path: Path, example: dict[str, object]
) -> None:
    facts = _runtime_example(tmp_path, example)
    complete = example.get("complete", example["name"] == "relative")
    if not complete:
        assert not facts.coverage.full_scope
    targets = [item for item in facts.imports if isinstance(item, LocalTarget)]
    for target in targets:
        if target.runtime_file is not None:
            # A type-only import keeps the compiler's file; a value import only a proven runtime.
            expected = (
                "src/pkg/types.ts" if example.get("type_only") else example.get("runtime_path")
            )
            assert target.runtime_file == (expected or "src/runtime.js")
