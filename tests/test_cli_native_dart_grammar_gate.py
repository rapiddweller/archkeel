# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-342: a Dart source that the pinned grammar cannot parse soundly gives a named gap (#1031).

Consumer: `archkeel validate` on a Dart project, through the release core. One source holds the
form and the rest of the project is clean. Each form must give UNKNOWN for each import rule, and
the collection gaps must name the file and the cause: never a silent PASS. The control source keeps
the verdict of a clean project, so the plants test the source and not a broken fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_native_dart_imports import BASE, all_unknown, decided, project
from test_cli_native_python_imports import rows, verdict

# The cause that the explanation names, and the source that holds the form.
FORMS: dict[str, tuple[str, str | bytes]] = {
    "missing-brace": ("syntax errors prevent complete source facts", "class Model {\n"),
    "keywords": ("syntax errors prevent complete source facts", "class class class;\n"),
    "open-parameters": ("syntax errors prevent complete source facts", "void f( {\n"),
    "directive-without-semicolon": (
        "syntax errors prevent complete source facts",
        "import 'package:shop/data/repo.dart'\nclass Model {}\n",
    ),
    "invalid-utf8": ("syntax errors prevent complete source facts", b"class A {}\n\xff\xfe\n"),
    "future-language-version": (
        "Dart language override is outside supported range 2.12 through 3.12.",
        "// @dart=3.99\nclass Model {}\n",
    ),
    "old-language-version": (
        "Dart language override is outside supported range 2.12 through 3.12.",
        "// @dart=2.7\nclass Model {}\n",
    ),
}


def test_the_control_source_keeps_the_verdict_of_a_clean_project(
    release_core: Path, tmp_path: Path
) -> None:
    result = verdict(release_core, project(tmp_path, BASE))
    assert rows(result) == decided(), result["frame"]["explained"]


@pytest.mark.parametrize("name", sorted(FORMS))
def test_a_source_that_the_grammar_cannot_parse_soundly_is_a_named_gap(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    cause, source = FORMS[name]
    files = {**BASE, "lib/domain/model.dart": source}
    result = verdict(release_core, project(tmp_path, files))
    all_unknown(result)
    named = [
        gap
        for gap in result["frame"]["collection_gaps"]
        if gap["kind"] == "exception_gap"
        and any(subject.startswith("lib/domain/model.dart:") for subject in gap["subjects"])
        and cause in gap["reason"]
    ]
    assert len(named) == 1, result["frame"]["collection_gaps"]


def test_a_pubspec_without_an_sdk_constraint_keeps_the_verdict(
    release_core: Path, tmp_path: Path
) -> None:
    # AD-342: only a constraint outside 2.12 through 3.12 is a gap; no constraint is no gap.
    files = {**BASE, "pubspec.yaml": "name: shop\n"}
    result = verdict(release_core, project(tmp_path, files))
    assert rows(result) == decided(), result["frame"]["explained"]
