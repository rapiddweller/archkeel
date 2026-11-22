# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1052: a declaration names a gap site by its name, through the release core.

Consumer: a CI job that reads the row of each rule and the exit code. Contract 3.20.0 lets a
`trojan_horse_reach` record name its site by `name` instead of a form. A matched declaration lets
the rules
decide and says "PASS under N declared reaches"; a moved site, a twin site and a binding that
another module can reach are named defects and apply nothing. Python 3.12 runs the truth of each
plant: the declared reach must not hide an import that really happens.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from test_cli_native_python_imports import command, rows
from test_cli_python_gap_effects import ON_FILES
from test_cli_python_trojan_horse_reach import declaration, scanned

VERSION = "3.20.0"
MODEL = "src/app/service/model.py"
PAGE = "src/app/client/page.py"
# Pickle bytes that import `app.service.secret` and read `KEY`: a real import through `pickle`.
BLOB = "b'capp.service.secret\\nKEY\\n.'"


def named(**fields: Any) -> dict[str, Any]:
    record = declaration(id="D-NAME", name="__self__", line=1) | fields
    del record["trojan_horse"]
    return record


def pickle_declaration() -> dict[str, Any]:
    return named(id="D-PICKLE", name="pickle")


def run(
    root: Path, files: dict[str, str], declared: list[dict[str, Any]], binary: Path
) -> dict[str, Any]:
    return scanned(binary, root, files, declared, version=VERSION)


def imports_secret(root: Path) -> bool:
    code = (
        "import sys; sys.path.insert(0, 'src'); import app.client.page; "
        "print('app.service.secret' in sys.modules)"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", code], cwd=root, capture_output=True, text=True, check=True
    )
    return done.stdout.strip() == "True"


def test_a_trojan_horse_string_is_declared_by_name_and_the_pass_says_so(
    release_core: Path, tmp_path: Path
) -> None:
    files = {MODEL: "KEY = '__self__'\n"}
    undeclared = run(tmp_path / "a", files, [], release_core)
    assert "UNKNOWN" in set(rows(undeclared).values()), undeclared

    result = run(tmp_path / "b", files, [named()], release_core)
    assert set(rows(result).values()) == {"PASS"}, result
    (row,) = result["frame"]["trojan_horse_reach"]
    assert row["trojan_horse"] == "__self__" and row["rationale"], row
    text = command(release_core, tmp_path / "b", "--text").stdout
    assert "pass under 1 declared reach" in text, text


def test_a_moved_site_is_unmatched_and_a_twin_needs_a_count(
    release_core: Path, tmp_path: Path
) -> None:
    moved = run(tmp_path / "a", {MODEL: "KEY = '__self__'\n"}, [named(line=2)], release_core)
    kinds = {gap["kind"] for gap in moved["gaps"]}
    assert "trojan_horse_reach.unmatched" in kinds and moved["exit_code"] == 2, moved["gaps"]
    assert "PASS" not in {v for k, v in rows(moved).items() if k not in ON_FILES}

    twin = {MODEL: "KEY = ('__self__', '__self__')\n"}
    one = run(tmp_path / "b", twin, [named()], release_core)
    assert "trojan_horse_reach.ambiguous" in {gap["kind"] for gap in one["gaps"]}, one["gaps"]
    two = run(tmp_path / "c", twin, [named(count=2)], release_core)
    assert set(rows(two).values()) == {"PASS"}, two
    three = run(tmp_path / "d", twin, [named(count=3)], release_core)
    assert "trojan_horse_reach.unmatched" in {gap["kind"] for gap in three["gaps"]}, three["gaps"]


def test_a_declared_import_that_another_module_reaches_by_attribute_applies_nothing(
    release_core: Path, tmp_path: Path
) -> None:
    declared = [pickle_declaration()]
    attribute = f"import app.service.model as model\nmodel.pickle.loads({BLOB})\n"
    for name, use in {
        "attribute": attribute,
        "from-import": f"from app.service.model import pickle\npickle.loads({BLOB})\n",
    }.items():
        root = tmp_path / name
        result = run(root, {MODEL: "import pickle\n", PAGE: use}, declared, release_core)
        # Python imports the forbidden module through the declared name.
        assert imports_secret(root)
        assert rows(result)["CLIENT-NO-SECRET"] != "PASS", (name, result)
        kinds = {gap["kind"] for gap in result["gaps"]}
        assert "trojan_horse_reach.invalid" in kinds, (name, result["gaps"])


def test_a_declared_import_that_no_module_reaches_applies(
    release_core: Path, tmp_path: Path
) -> None:
    declared = [pickle_declaration()]
    page = "import app.service.model as model\nVALUE = model.VALUE\n"
    files = {MODEL: "import pickle\nVALUE = 1\n", PAGE: page}
    result = run(tmp_path, files, declared, release_core)
    assert set(rows(result).values()) == {"PASS"}, result


def test_a_fail_that_rests_on_a_declared_load_says_so_and_an_observed_one_does_not(
    release_core: Path, tmp_path: Path
) -> None:
    declared = [named(module="app.client.page", line=2, loads=["app.service.secret"])]
    page = "import app.service.model as model\nKEY = '__self__'\n"
    result = run(tmp_path / "a", {PAGE: page}, declared, release_core)
    assert rows(result)["CLIENT-NO-SECRET"] == "FAIL", result
    assert result["frame"]["fail_from_declared_reach"] == {"CLIENT-NO-SECRET": ["D-NAME"]}
    text = command(release_core, tmp_path / "a", "--text").stdout
    assert "FAIL from a declared reach: CLIENT-NO-SECRET (declared by D-NAME)" in text, text

    seen = page + "import app.service.secret\n"
    result = run(tmp_path / "b", {PAGE: seen}, declared, release_core)
    assert rows(result)["CLIENT-NO-SECRET"] == "FAIL", result
    assert "fail_from_declared_reach" not in result["frame"], result["frame"]


def test_a_covers_list_clears_the_exposure_of_the_modules_it_names_and_no_other(
    release_core: Path, tmp_path: Path
) -> None:
    """AD-1056: `covers` names the modules whose use of the bound name the contract accepts."""
    harmless = "import app.service.model as model\nSIZE = len(model.pickle.dumps(1))\n"
    declared = [pickle_declaration() | {"covers": ["app.client"]}]
    covered = run(
        tmp_path / "covered", {MODEL: "import pickle\n", PAGE: harmless}, declared, release_core
    )
    assert not imports_secret(tmp_path / "covered"), "the covered use really loads nothing"
    assert set(rows(covered).values()) == {"PASS"}, covered
    (row,) = covered["frame"]["trojan_horse_reach"]
    assert row["covered"] == ["app.client.page"], row
    text = command(release_core, tmp_path / "covered", "--text").stdout
    assert "Covered uses of the bound name: app.client.page" in text, text

    # A module that `covers` does not name stays refused, and Python really imports the module.
    attribute = f"import app.service.model as model\nmodel.pickle.loads({BLOB})\n"
    other = [pickle_declaration() | {"covers": ["app.other"]}]
    root = tmp_path / "uncovered"
    refused = run(root, {MODEL: "import pickle\n", PAGE: attribute}, other, release_core)
    assert imports_secret(root)
    assert rows(refused)["CLIENT-NO-SECRET"] != "PASS", refused
    assert "trojan_horse_reach.invalid" in {gap["kind"] for gap in refused["gaps"]}, refused["gaps"]
    assert "covered" not in json.dumps(refused["frame"].get("trojan_horse_reach", [])), refused


def test_a_module_that_reads_any_attribute_by_a_computed_name_is_exposed(
    release_core: Path, tmp_path: Path
) -> None:
    """AD-1058: `getattr(m, 'pick' + 'le')`, `m.__dict__[n]` and `vars(m)[n]` reach the bound name.

    The importer builds the name at run time, so no attribute or text of it is in the scan. The
    declaration on `import pickle` is refused, and Python really imports the secret module.
    """
    declared = [pickle_declaration()]
    head = "import app.service.model as model\nn = 'pick' + 'le'\n"
    plants = {
        "getattr": f"{head}getattr(model, n).loads({BLOB})\n",
        "dict": f"{head}model.__dict__[n].loads({BLOB})\n",
        "vars": f"{head}vars(model)[n].loads({BLOB})\n",
        "getattribute": f"{head}model.__getattribute__(n).loads({BLOB})\n",
    }
    for name, use in plants.items():
        root = tmp_path / name
        result = run(root, {MODEL: "import pickle\n", PAGE: use}, declared, release_core)
        assert imports_secret(root), name
        assert rows(result)["CLIENT-NO-SECRET"] != "PASS", (name, result)
        assert "trojan_horse_reach.invalid" in {gap["kind"] for gap in result["gaps"]}, name
        assert "assuming" not in result["frame"], (name, result["frame"])


def test_a_plain_import_of_the_same_name_elsewhere_is_no_use_of_the_binding(
    release_core: Path, tmp_path: Path
) -> None:
    """AD-1058: another module's own `import pickle` is its own site, not a use of the binding."""
    other = "src/app/service/other.py"
    first = pickle_declaration()
    second = named(id="D-OTHER", name="pickle", module="app.service.other")
    files = {MODEL: "import pickle\n", other: "import pickle\nSIZE = 1\n"}
    result = run(tmp_path, files, [first, second], release_core)

    assert set(rows(result).values()) == {"PASS"}, result
    assert {row["id"] for row in result["frame"]["trojan_horse_reach"]} == {"D-PICKLE", "D-OTHER"}
