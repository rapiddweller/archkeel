# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#749: one leading byte order mark in `archkeel.toml` is read by the shell and by the core alike.

Consumer: a user whose editor saves `archkeel.toml` as UTF-8 with a BOM. The core reads the file
itself and takes one leading BOM. The shell checks the same bytes against its request; it must take
exactly one too. Two BOMs and a BOM inside the text are refused by both, and never give PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from corpus_support import commit_tree
from rust_repository import outcome, repository
from test_cli_native_dart_imports import BASE, project
from test_cli_native_python_imports import rows, verdict

BOM = "﻿"
# name: (a change of the text of archkeel.toml, exit code, status)
CASES = {
    "no BOM": (lambda text: text, 0, "PASS"),
    "one BOM": (lambda text: BOM + text, 0, "PASS"),
    "two BOMs": (lambda text: BOM + BOM + text, 2, "UNKNOWN"),
    "a BOM in the middle": (
        lambda text: text.replace("namespace", BOM + "namespace"),
        2,
        "UNKNOWN",
    ),
}


@pytest.mark.parametrize("command", ["validate", "report"])
@pytest.mark.parametrize(("change", "code", "status"), CASES.values(), ids=CASES.keys())
def test_the_shell_and_the_core_read_one_bom_and_refuse_more(
    tmp_path: Path, core_binary: Path, command: str, change: object, code: int, status: str
) -> None:
    root = repository(tmp_path, core_binary)
    config = root / "archkeel.toml"
    config.write_bytes(change(config.read_text()).encode("utf-8"))  # type: ignore[operator]
    commit_tree(root)

    found, document = outcome(root, command)

    assert (found, document["status"]) == (code, status), document
    assert (document.get("refusal") is None) == (code == 0), document.get("refusal")


def test_a_dart_file_with_a_bom_gives_the_verdict_and_the_line_of_one_without(
    release_core: Path, tmp_path: Path
) -> None:
    """The Dart half of #749: the BOM at the start of line 1 must not move the import's line."""
    seen = []
    for name, mark in (("plain", b""), ("bom", b"\xef\xbb\xbf")):
        files = {
            **BASE,
            "lib/domain/model.dart": mark + b"import '../data/repo.dart';\nclass Model {}\n",
        }
        result = verdict(release_core, project(tmp_path / name, files))
        places = {(place["path"], place["line"]) for place in result["frame"]["locations"].values()}
        seen.append((rows(result), result["exit_code"], places & {("lib/domain/model.dart", 1)}))
    assert seen[0] == seen[1]
    assert seen[1][0]["FORBID"] == "FAIL" and seen[1][2] == {("lib/domain/model.dart", 1)}
