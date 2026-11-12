# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native resolver keeps suffix inference and compiler diagnostics explicit."""

import json

import pytest
from recorded_typescript import collect as recorded_collect
from test_collector_native_imports import _request, _view, _write

from archkeel.analyzer.process import ProcessCollector
from archkeel.cli.observe import TYPESCRIPT_COLLECTOR, executable
from archkeel.ir.facts import BuiltinTarget, ExternalPackageTarget, LocalTarget, SourceFacts


def _facts(root, files, config):
    _write(root, {**files, "tsconfig.json": json.dumps(config)})
    request = _request(root, "app", "tsconfig.json")
    facts = ProcessCollector((str(executable(TYPESCRIPT_COLLECTOR)),)).collect(request)
    assert isinstance(facts, SourceFacts), facts
    assert _view(facts) == _view(recorded_collect(request))
    return facts


@pytest.mark.parametrize("spec", ["src/**", "src/**/", "src/foo**", "src/foo**/"])
def test_recursive_tail_diagnostic_keeps_existing_non_component_star_rule(tmp_path, spec):
    facts = _facts(tmp_path, {"src/main.ts": "export {};"}, {"include": [spec]})
    assert not facts.coverage.full_scope
    assert any("recursive wildcard" in gap.title for gap in facts.coverage.gaps)


@pytest.mark.parametrize("target", ["types.unknown", "types"])
def test_package_worker_does_not_turn_unsupported_suffix_into_plain_family(tmp_path, target):
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": 'import "pkg";',
            "node_modules/pkg/package.json": json.dumps({"types": target}),
            f"node_modules/pkg/{target}.ts": "export {};",
            "node_modules/pkg/types.ts": "export {};",
        },
        {"compilerOptions": {"module": "commonjs"}, "include": ["src"]},
    )
    assert any(
        isinstance(item, ExternalPackageTarget) and item.package == "pkg" for item in facts.imports
    )


@pytest.mark.parametrize("target", ["a.ts", "a.unknown"])
def test_paths_exact_known_target_and_unknown_suffix_inference_stay_distinct(tmp_path, target):
    facts = _facts(
        tmp_path,
        {
            "src/main.ts": 'import "alias";',
            f"src/{target}": "export {};",
            f"src/{target}.ts": "export {};",
        },
        {
            "compilerOptions": {
                "module": "commonjs",
                "baseUrl": ".",
                "paths": {"alias": [f"src/{target}"]},
            },
            "include": ["src"],
        },
    )
    expected = target if target == "a.ts" else f"{target}.ts"
    assert any(
        isinstance(item, LocalTarget) and item.file == f"src/{expected}" for item in facts.imports
    )


def test_declaration_cts_keeps_written_commonjs_loader_semantics(tmp_path):
    facts = _facts(
        tmp_path,
        {"src/main.d.cts": 'const fs = require("node:fs");'},
        {"compilerOptions": {"moduleResolution": "node"}, "files": ["src/main.d.cts"]},
    )
    assert any(isinstance(target, BuiltinTarget) for target in facts.imports)
    assert not any("Unproven or shadowed require" in gap.title for gap in facts.coverage.gaps)
