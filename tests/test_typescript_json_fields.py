# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Open JSON field identity preserves presence independently of field value."""

import json

import pytest

from archkeel.analyzer.typescript import config
from archkeel.analyzer.typescript.resolve import Found, Resolver, Unknown


@pytest.mark.parametrize("value", [None, False, 0, "", [], {}, "present"])
def test_json_field_presence_is_independent_of_null_and_falsy_values(value):
    record = {"arbitrary.user-field": value}
    assert config.has_field(record, "arbitrary.user-field") is True
    assert config.has_field(record, "missing") is False
    assert record == {"arbitrary.user-field": value}


def _write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    snapshot = config.Snapshot(str(root))
    return config.load_config(snapshot, "tsconfig.json", ("src",)), snapshot


@pytest.mark.parametrize("field", ["baseUrl", "paths"])
@pytest.mark.parametrize("present", [False, True])
def test_real_config_overlay_distinguishes_an_absent_field_from_null(tmp_path, field, present):
    options = {field: None} if present else {}
    inherited = {field: "." if field == "baseUrl" else {"@x": ["x.ts"]}}
    selected, _ = _write(
        tmp_path,
        {
            "tsconfig.json": json.dumps({"extends": "./base/base.json", "compilerOptions": options}),
            "base/base.json": json.dumps({"compilerOptions": inherited}),
            "src/main.ts": "export {};",
        },
    )
    if field == "baseUrl":
        assert selected.options.base_url == (None if present else "base")
    else:
        # The input config owns a declared paths field even when that value is invalid null.
        assert selected.options.paths == (() if present else (("@x", ("x.ts",)),))
        assert selected.options.paths_base == ("." if present else "base")


@pytest.mark.parametrize("value", [None, False, 0, "", [], {}])
def test_real_project_references_presence_remains_a_gap_for_falsy_values(tmp_path, value):
    _, snapshot = _write(
        tmp_path,
        {"tsconfig.json": json.dumps({"references": value}), "src/main.ts": "export {};"},
    )
    assert "Project references require separately observed projects" in snapshot.problems


@pytest.mark.parametrize("value", [None, False, 0, "", [], {}])
@pytest.mark.parametrize("specifier", ["example", "example/sub"])
def test_real_package_lookup_never_ignores_present_types_versions(tmp_path, value, specifier):
    _, snapshot = _write(
        tmp_path,
        {
            "tsconfig.json": "{}",
            "src/main.ts": "export {};",
            "node_modules/example/package.json": json.dumps({"typesVersions": value}),
            "node_modules/example/index.d.ts": "export interface A {}",
            "node_modules/example/sub/package.json": json.dumps({"typesVersions": value}),
            "node_modules/example/sub/index.d.ts": "export interface A {}",
        },
    )
    selected = config.load_config(snapshot, "tsconfig.json", ("src",))
    result = Resolver(snapshot, selected).resolve(specifier, "src/main.ts", None)
    assert isinstance(result, Unknown) and "typesVersions" in result.reason


def test_absent_types_versions_allows_the_package_index(tmp_path):
    selected, snapshot = _write(
        tmp_path,
        {
            "tsconfig.json": "{}",
            "src/main.ts": "export {};",
            "node_modules/example/package.json": "{}",
            "node_modules/example/index.d.ts": "export interface A {}",
        },
    )
    result = Resolver(snapshot, selected).resolve("example", "src/main.ts", None)
    assert isinstance(result, Found) and result.path == "node_modules/example/index.d.ts"
