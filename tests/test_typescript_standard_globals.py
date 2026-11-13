# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Standard globals require a supported captured library environment."""

import pytest
from test_typescript_source_input import _facts


def _environment(tmp_path, options):
    return _facts(
        tmp_path,
        {"src/main.ts": "function f() {}"},
        {"compilerOptions": options, "files": ["src/main.ts"]},
    )


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
    facts = _environment(tmp_path, compiler)
    assert not facts.coverage.full_scope and facts.coverage.gaps


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
def test_script_environment_options_equal_the_recorded_python_collector(
    tmp_path, compiler, global_scripts
):
    facts = _facts(
        tmp_path,
        {
            "src/scene.js": (
                "var Scene = (function () { function create() {} return { create }; })();"
            ),
            "src/main.js": "Scene.create();",
        },
        {"compilerOptions": {"allowJs": True, **compiler}, "include": ["src"]},
    )
    assert len(facts.files) == 2
