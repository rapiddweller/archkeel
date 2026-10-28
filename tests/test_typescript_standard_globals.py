# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Standard globals require a supported captured library environment."""

import hashlib
import json

import pytest
from test_typescript_config import _config

from archkeel.analyzer.typescript.config import (
    ModuleDetection,
    Options,
    ScriptTarget,
    StandardLibrary,
    standard_globals,
)
from archkeel.analyzer.typescript.resolve import Found, Resolver


def _environment(tmp_path, options):
    payload = json.dumps({"compilerOptions": options, "files": ["main.ts"]})
    return _config(tmp_path, {"main.ts": "export {};"}, payload)


@pytest.mark.parametrize(
    ("compiler", "present", "missing"),
    [
        ({}, {"String", "Boolean", "Math", "document", "undefined"}, {"Map", "Promise"}),
        ({"target": "es2015"}, {"String", "Map", "Promise", "document"}, {"WeakRef"}),
        ({"target": "es2022"}, {"Map", "Promise", "WeakMap", "document"}, {"Iterator"}),
        ({"lib": ["ES2022", "DoM"]}, {"Map", "document", "CSS", "Event"}, {"ELK"}),
        ({"lib": ["dom"]}, {"document", "location"}, {"String", "Map"}),
        (
            {"lib": ["es5"], "target": "es2022"},
            {"String", "undefined"},
            {"Map", "document", "Event"},
        ),
        ({"lib": []}, set(), {"String", "document", "Map"}),
        ({"noLib": True}, set(), {"String", "document", "Map"}),
    ],
)
def test_supported_library_environments_only_prove_their_own_globals(
    tmp_path, compiler, present, missing
):
    config, snapshot = _environment(tmp_path, compiler)
    assert not config.partial and not snapshot.problems
    names = standard_globals(config.options)
    assert present <= names
    assert not missing & names
    assert not {"ELK", "ArchkeelGraphScene", "MissingGlobal", "decider", "perspectives"} & names
    assert (
        snapshot.inputs["tsconfig.json"][0]
        == hashlib.sha256((tmp_path / "tsconfig.json").read_bytes()).hexdigest()
    )


@pytest.mark.parametrize(
    "compiler",
    [
        {"lib": ["es2022", "unobserved.library"]},
        {"lib": ["es2022", "dom"], "libReplacement": True},
    ],
)
def test_unmodeled_library_selection_never_partly_proves_a_standard_environment(tmp_path, compiler):
    (tmp_path / "dependency.ts").write_text("export const value = 1;")
    config, snapshot = _environment(tmp_path, compiler)
    assert not config.partial and not snapshot.problems and not config.options.unmodeled
    assert config.options.lib_unmodeled
    assert standard_globals(config.options) == frozenset()
    source_edge = Resolver(snapshot, config).resolve("./dependency", "main.ts", None)
    assert isinstance(source_edge, Found) and source_edge.path == "dependency.ts"


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"types": []},
        {"types": ["node"]},
        {"types": ["vite/client", "node", "vitest/globals"]},
        {"typeRoots": []},
        {"typeRoots": ["./ambient"]},
        {"types": ["node"], "typeRoots": ["./ambient"]},
        {"libReplacement": False},
    ],
)
def test_types_and_type_roots_add_globals_and_keep_the_standard_environment(tmp_path, options):
    config, snapshot = _environment(tmp_path, {"lib": ["es2022", "dom"], **options})
    assert not config.partial and not snapshot.problems and not config.options.unmodeled
    assert not config.options.lib_unmodeled
    names = standard_globals(config.options)
    assert {"Map", "String", "document", "Math", "Date"} <= names
    # A types package adds names the catalog does not hold; they stay unproved (AD-274).
    assert not {"process", "__dirname", "describe", "Buffer"} & names


@pytest.mark.parametrize(
    "compiler",
    [
        {"lib": "dom"},
        {"lib": [42]},
        {"noLib": "true"},
        {"types": "node"},
        {"typeRoots": False},
        {"libReplacement": "false"},
        {"lib": ["dom"], "noLib": True},
    ],
)
def test_malformed_or_conflicting_ambient_options_are_explicitly_partial(tmp_path, compiler):
    config, snapshot = _environment(tmp_path, compiler)
    assert config.partial and snapshot.problems


def test_inherited_libraries_are_captured_and_child_selection_replaces_them(tmp_path):
    config, snapshot = _config(
        tmp_path,
        {
            "main.ts": "export {};",
            "base.json": json.dumps({"compilerOptions": {"lib": ["es2022", "dom"]}}),
        },
        json.dumps({"extends": "./base.json", "compilerOptions": {"lib": ["es5"]}}),
    )
    assert not config.partial and not snapshot.problems
    assert config.options.libs == (StandardLibrary.ES5,)
    assert "String" in standard_globals(config.options)
    assert not {"Map", "document"} & standard_globals(config.options)
    assert {"base.json", "tsconfig.json"} <= snapshot.inputs.keys()


@pytest.mark.parametrize(
    "changes",
    [{"libs": ("dom",)}, {"libs": [StandardLibrary.DOM]}, {"no_lib": 1}, {"lib_unmodeled": 1}],
)
def test_standard_environment_has_nominal_typed_fields(changes):
    with pytest.raises(TypeError):
        Options(**changes)


def test_catalog_proves_the_target_default_library_and_no_member_resolution():
    assert Options().libs is None and Options().no_lib is False
    names = standard_globals(Options(target=ScriptTarget.ES2022))
    assert {"Math", "Map", "document"} <= names
    assert not {"Math.max", "ELK"} & names


@pytest.mark.parametrize(
    ("value", "partial"),
    [("force", False), ("FORCE", False), ("Auto", False), ("bogus", True), (True, True)],
)
def test_module_detection_is_read_like_the_compiler_reads_it(tmp_path, value, partial):
    config, snapshot = _environment(tmp_path, {"moduleDetection": value})
    assert config.partial is partial and bool(snapshot.problems) is partial
    if not partial:
        assert config.options.module_detection is ModuleDetection(value.lower())


@pytest.mark.parametrize(
    ("compiler", "global_scripts"),
    [
        ({}, True),
        ({"moduleDetection": "auto"}, True),
        ({"moduleDetection": "legacy"}, True),
        ({"moduleDetection": "force"}, False),
        ({"module": "esnext", "moduleResolution": "bundler"}, True),
        ({"module": "preserve", "moduleResolution": "bundler"}, True),
        ({"module": "node16", "moduleResolution": "node16"}, False),
        ({"module": "node18", "moduleResolution": "node16"}, False),
        ({"module": "node20", "moduleResolution": "node16"}, False),
        ({"module": "nodenext", "moduleResolution": "nodenext"}, False),
        (
            {"module": "nodenext", "moduleResolution": "nodenext", "moduleDetection": "legacy"},
            False,
        ),
    ],
)
def test_a_source_file_without_import_or_export_is_a_global_script_only_when_the_options_allow(
    tmp_path, compiler, global_scripts
):
    config, _ = _environment(tmp_path, compiler)
    assert config.options.scripts_are_global is global_scripts
