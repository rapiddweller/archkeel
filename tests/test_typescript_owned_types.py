# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compiler values cross the configuration/resolver API as nominal owned types."""

import json
from enum import Enum
from typing import get_type_hints

import pytest

from archkeel.analyzer.typescript import config, resolve


def _loaded(tmp_path, options):
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src/main.ts").write_text("export {};")
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": options, "include": ["src"]})
    )
    snapshot = config.Snapshot(str(tmp_path))
    return config.load_config(snapshot, "tsconfig.json", ("src",)), snapshot


@pytest.mark.parametrize(
    ("field", "type_name"),
    [("module", "ModuleKind"), ("module_resolution", "ModuleResolution"), ("target", "ScriptTarget")],
)
def test_option_fields_have_nominal_owner_types(field, type_name):
    annotation = get_type_hints(config.Options)[field]
    assert annotation != str | None, (field, annotation)
    owned = getattr(config, type_name)
    assert issubclass(owned, Enum) and not issubclass(owned, str)
    assert annotation == owned | None


def test_derived_configuration_returns_owned_types():
    assert get_type_hints(config.Options.emit_module.fget)["return"] != str
    assert get_type_hints(config.Options.resolution.fget)["return"] != str
    assert config.Options().emit_module is config.ModuleKind.COMMONJS
    assert config.Options().resolution is config.ModuleResolution.NODE10


def test_wire_values_convert_once_and_node_alias_is_canonical(tmp_path):
    loaded, snapshot = _loaded(
        tmp_path, {"module": "CoMmOnJs", "moduleResolution": "NoDe", "target": "ES2020"}
    )
    assert isinstance(loaded.options.module, Enum)
    assert loaded.options.module is config.ModuleKind.COMMONJS
    assert loaded.options.module_resolution is config.ModuleResolution.NODE10
    assert loaded.options.target is config.ScriptTarget.ES2020
    assert loaded.partial is False and not snapshot.problems


@pytest.mark.parametrize("field", ["module", "moduleResolution", "target"])
def test_unrecognized_wire_value_is_partial_with_original_diagnostic(tmp_path, field):
    loaded, snapshot = _loaded(tmp_path, {field: "future-unsupported"})
    assert loaded.partial
    assert f"Compiler option 6046: argument for '{field}' is not valid." in snapshot.problems


def test_resolver_format_and_source_kinds_are_nominal():
    assert get_type_hints(resolve.Resolver.resolve)["mode"] != resolve.Format | None or (
        hasattr(resolve, "ModuleFormat") and resolve.Format is resolve.ModuleFormat
    )
    assert hasattr(resolve, "ModuleFormat"), "ModuleFormat must be resolver-owned"
    assert not issubclass(resolve.ModuleFormat, str)
    assert get_type_hints(resolve.Resolver.resolve)["mode"] == resolve.ModuleFormat | None
    assert resolve.Kinds == tuple[resolve.SourceKind, ...]


def test_package_protocol_conversion_keeps_unknown_conditions_unknown():
    assert resolve.Resolver._export_condition(
        {"future-condition": "./unsupported.js", "default": "./fallback.js"}, True
    ) == resolve.Unknown("Package exports condition is not observed: future-condition")
    assert resolve.Resolver._export_condition(
        {"require": "./cjs.js", "import": "./esm.js"}, True
    ) == "./esm.js"
    assert resolve.Resolver._export_condition(
        {"require": "./cjs.js", "import": "./esm.js"}, False
    ) == "./cjs.js"


def test_formats_are_typed_at_the_resolver_consumer_boundary(tmp_path):
    loaded, snapshot = _loaded(tmp_path, {"module": "NodeNext"})
    (tmp_path / "package.json").write_text('{"type":"module"}')
    resolver = resolve.Resolver(snapshot, loaded)
    result = resolver.format_of("src/main.ts")
    assert isinstance(result, Enum)
    assert result is resolve.ModuleFormat.ESM
    assert resolver.format_of("src/main.cts") is resolve.ModuleFormat.CJS
