# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A Node declaration describes the host. Only a stable binding can use that evidence (#832)."""

from pathlib import Path

import pytest
from test_collector_false_pass_ts_preload import _node, _preload, _scripts, _validate

CONFIG = '{"compilerOptions":{"module":"commonjs","lib":["ES2022"]},"include":["src"]}'
USES = "export const a = process.env.A;\nexport const b = process.env.B;\n"
DECLARATION = {"src/a/host.d.ts": "declare var process: NodeJS.Process;\n"}
NODE_TYPES = {
    "node_modules/@types/node/package.json": '{"name":"@types/node","types":"index.d.ts"}',
    "node_modules/@types/node/index.d.ts": (
        "declare namespace NodeJS { interface Process { env: Record<string,string|undefined> } }\n"
        "declare var process: NodeJS.Process;\n"
    ),
}


@pytest.mark.parametrize(
    ("files", "status"),
    [
        ({}, "UNKNOWN"),
        (DECLARATION, "PASS"),
        (
            {**DECLARATION, "src/a/boot.ts": "globalThis.process = Object.create(null);\n"},
            "UNKNOWN",
        ),
        (
            {
                **DECLARATION,
                **_scripts("node -r preload src/a/a.js"),
                **_preload("globalThis.process = Object.create(null);\n"),
            },
            "UNKNOWN",
        ),
        (
            {
                **DECLARATION,
                "src/a/a.ts": 'import {hidden as process} from "../b/b";\nprocess();\n',
            },
            "FAIL",
        ),
    ],
    ids=["no-declaration", "declared", "reassigned", "preload", "shadowed"],
)
def test_node_process_needs_host_evidence(
    tmp_path: Path, release_core: Path, files: dict[str, str], status: str
) -> None:
    frame = _validate(
        tmp_path, release_core, {"tsconfig.json": CONFIG, "src/a/a.ts": USES, **NODE_TYPES, **files}
    )["frame"]
    assert frame["rules"]["REQUIRES"][1] == status, frame["collection_gaps"]
    if status == "PASS":
        assert (
            "the runtime supplies any host global proved by a project declaration"
            in frame["premise"]
        )
    if "package.json" in files:
        child = _node(
            tmp_path / "repo",
            "-r",
            "preload",
            "-e",
            "if (process === require('node:process')) throw Error('expected replacement');",
        )
        assert child.returncode == 0, child.stderr
        assert any(
            frame["locations"][site]["path"] == "node_modules/preload/index.js"
            for gap in frame["collection_gaps"]
            if gap["reason"] == "Script global process is replaced by a file outside the scan roots"
            for site in gap["evidence"]
        )
    if not files:
        [gap] = [
            gap
            for gap in frame["collection_gaps"]
            if gap["reason"] == "Script global process has no unique unconditional publication"
        ]
        places = [frame["locations"][site] for site in gap["evidence"]]
        assert {site["line"] for site in places if site["path"] == "src/a/a.ts"} == {1, 2}
