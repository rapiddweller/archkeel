# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Node environment-file options can change preload runtime resolution."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_collector_false_pass_ts_preload import PATCH, _node, _scripts, _validate


def test_npmrc_conditions_apply_to_package_script_preload(
    tmp_path: Path, release_core: Path
) -> None:
    command = "node --require hook -e \"console.log('SCRIPT')\""
    extra = {
        "package.json": json.dumps({"name": "app", "scripts": {"start": command}}),
        ".npmrc": "node-options=--conditions=types\n",
        "node_modules/hook/package.json": (
            '{"name":"hook","exports":{".":{"types":"./custom.cjs","require":"./ordinary.cjs"}}}'
        ),
        "node_modules/hook/custom.cjs": PATCH + "console.log('NPM_CUSTOM_TYPES');\n",
        "node_modules/hook/ordinary.cjs": "module.exports = {};\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = subprocess.run(
        ["npm", "run", "start"],
        cwd=tmp_path / "repo",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "NPM_CUSTOM_TYPES" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]
    assert any(
        "unobserved Node execution context" in gap["reason"] for gap in frame["collection_gaps"]
    )


def test_env_file_conditions_apply_to_transitive_preload_import(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        **_scripts("node --env-file=.env --require hook src/a/a.js"),
        ".env": "NODE_OPTIONS=--conditions=types\n",
        "node_modules/hook/package.json": '{"name":"hook","main":"index.js"}',
        "node_modules/hook/index.js": "require('dep');\n",
        "node_modules/dep/package.json": (
            '{"name":"dep","exports":{".":{"types":"./custom.cjs","require":"./ordinary.cjs"}}}'
        ),
        "node_modules/dep/custom.cjs": PATCH + "console.log('ENV_CUSTOM_TYPES');\n",
        "node_modules/dep/ordinary.cjs": "module.exports = {};\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = _node(
        tmp_path / "repo",
        "--env-file=.env",
        "--require",
        "hook",
        "-e",
        "console.log('MAIN')",
    )
    assert result.returncode == 0, result.stderr
    assert "ENV_CUSTOM_TYPES" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]
    assert any(
        "unobserved Node execution context" in gap["reason"] for gap in frame["collection_gaps"]
    )


def test_env_file_reference_with_unclassified_source_fails_closed(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        **_scripts("node --env-file=config/runtime.env --require hook src/a/a.js"),
        "config/runtime.env": "NODE_OPTIONS=--conditions=types\n",
        "node_modules/hook/package.json": (
            '{"name":"hook","exports":{".":{"types":"./custom.cjs","require":"./ordinary.cjs"}}}'
        ),
        "node_modules/hook/custom.cjs": "console.log('UNKNOWN_ENV_SOURCE');\n",
        "node_modules/hook/ordinary.cjs": "module.exports = {};\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = _node(
        tmp_path / "repo",
        "--env-file=config/runtime.env",
        "--require",
        "hook",
        "-e",
        "console.log('MAIN')",
    )
    assert result.returncode == 0, result.stderr
    assert "UNKNOWN_ENV_SOURCE" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]
    assert any(
        "unobserved Node execution context" in gap["reason"] for gap in frame["collection_gaps"]
    )


@pytest.mark.parametrize(
    ("flags", "node_args"),
    [
        ("--env-file='config/runtime.env'", ["--env-file=config/runtime.env"]),
        ("--env-file config/runtime.env", ["--env-file", "config/runtime.env"]),
        (
            "--env-file-if-exists=config/runtime.env",
            ["--env-file-if-exists=config/runtime.env"],
        ),
        (
            "--env-file-if-exists config/runtime.env",
            ["--env-file-if-exists", "config/runtime.env"],
        ),
        (
            "--env-file=empty.env --env-file-if-exists=config/runtime.env",
            ["--env-file=empty.env", "--env-file-if-exists=config/runtime.env"],
        ),
        (
            "--env-file=empty.env --env-file=config/runtime.env",
            ["--env-file=empty.env", "--env-file=config/runtime.env"],
        ),
    ],
    ids=(
        "required-quoted-path",
        "required-separated-path",
        "optional-equals-path",
        "optional-separated-path",
        "repeated-env-files",
        "repeated-required-env-files",
    ),
)
def test_documented_env_file_forms_cannot_leave_custom_preload_as_pass(
    tmp_path: Path,
    release_core: Path,
    flags: str,
    node_args: list[str],
) -> None:
    extra = {
        **_scripts(f"node {flags} --require hook src/a/a.js"),
        "empty.env": "OTHER=value\n",
        "config/runtime.env": "NODE_OPTIONS=--conditions=types\n",
        "node_modules/hook/package.json": (
            '{"name":"hook","exports":{".":{"types":"./custom.cjs","require":"./ordinary.cjs"}}}'
        ),
        "node_modules/hook/custom.cjs": "console.log('OPTIONAL_ENV_CUSTOM');\n",
        "node_modules/hook/ordinary.cjs": "module.exports = {};\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = _node(
        tmp_path / "repo",
        *node_args,
        "--require",
        "hook",
        "-e",
        "console.log('MAIN')",
    )
    assert result.returncode == 0, result.stderr
    assert "OPTIONAL_ENV_CUSTOM" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]
    assert any(
        "unobserved Node execution context" in gap["reason"] for gap in frame["collection_gaps"]
    )


def test_unknown_env_file_prefixed_option_is_unknown_for_named_preloads(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        **_scripts("node --env-file-future=config/runtime.env --require hook src/a/a.js"),
        "node_modules/hook/package.json": '{"name":"hook","main":"index.js"}',
        "node_modules/hook/index.js": "exports.ready = true;\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]


def test_missing_optional_env_file_is_a_control_for_the_real_node_command(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        **_scripts("node --env-file-if-exists=absent.env --require hook src/a/a.js"),
        "node_modules/hook/package.json": '{"name":"hook","main":"index.js"}',
        "node_modules/hook/index.js": "exports.ready = true;\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = _node(
        tmp_path / "repo",
        "--env-file-if-exists=absent.env",
        "--require",
        "hook",
        "-e",
        "console.log('OPTIONAL_MISSING_OK')",
    )
    assert result.returncode == 0, result.stderr
    assert "OPTIONAL_MISSING_OK" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] == "PASS", frame["rules"]


def test_npm_script_changed_cwd_cannot_leave_optional_env_file_as_pass(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        "package.json": json.dumps(
            {
                "name": "app",
                "scripts": {
                    "start": (
                        "cd sub && node --env-file-if-exists=runtime.env --require hook "
                        "-e 'console.log(1)'"
                    )
                },
            }
        ),
        "sub/runtime.env": "NODE_OPTIONS=--conditions=types\n",
        "node_modules/hook/package.json": (
            '{"name":"hook","exports":{".":{"types":"./custom.cjs","require":"./ordinary.cjs"}}}'
        ),
        "node_modules/hook/custom.cjs": PATCH + "console.log('SUB_ENV_CUSTOM');\n",
        "node_modules/hook/ordinary.cjs": "module.exports = {};\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = subprocess.run(
        ["npm", "run", "start"],
        cwd=tmp_path / "repo",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "SUB_ENV_CUSTOM" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]


def test_npm_script_changed_cwd_cannot_leave_relative_preload_as_pass(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        "package.json": json.dumps(
            {
                "name": "app",
                "scripts": {"start": "cd sub && node --require ./hook.cjs -e 'console.log(1)'"},
            }
        ),
        "hook.cjs": "module.exports = {};\n",
        "sub/hook.cjs": PATCH + "console.log('SUB_RELATIVE_PRELOAD');\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = subprocess.run(
        ["npm", "run", "start"],
        cwd=tmp_path / "repo",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "SUB_RELATIVE_PRELOAD" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]


def test_oversized_env_file_snapshot_refusal_withholds_preload_pass(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        **_scripts("node --env-file=.env --require hook src/a/a.js"),
        ".env": "NODE_OPTIONS=--conditions=types\n#" + ("x" * (4 * 1024 * 1024)),
        "node_modules/hook/package.json": (
            '{"name":"hook","exports":{".":{"types":"./custom.cjs","require":"./ordinary.cjs"}}}'
        ),
        "node_modules/hook/custom.cjs": "console.log('REFUSED_ENV_CUSTOM');\n",
        "node_modules/hook/ordinary.cjs": "module.exports = {};\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = _node(
        tmp_path / "repo",
        "--env-file=.env",
        "--require",
        "hook",
        "-e",
        "console.log('MAIN')",
    )
    assert result.returncode == 0, result.stderr
    assert "REFUSED_ENV_CUSTOM" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] == "UNKNOWN", frame["rules"]
    assert any(
        "Preload configuration .env cannot be read" in gap["reason"]
        for gap in frame["collection_gaps"]
    )


def test_separate_npm_options_without_custom_conditions_keep_safe_preload_pass(
    tmp_path: Path, release_core: Path
) -> None:
    extra = {
        "package.json": json.dumps(
            {"name": "app", "scripts": {"start": "node -e \"console.log('SAFE_SCRIPT')\""}}
        ),
        ".npmrc": "node-options=--require hook\n",
        "node_modules/hook/package.json": '{"name":"hook","main":"index.js"}',
        "node_modules/hook/index.js": "exports.ready = true;\n",
    }
    frame = _validate(tmp_path, release_core, extra)["frame"]
    result = subprocess.run(
        ["npm", "run", "start"],
        cwd=tmp_path / "repo",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "SAFE_SCRIPT" in result.stdout, result.stdout
    assert frame["rules"]["REQUIRES"][1] == "PASS", frame["rules"]
