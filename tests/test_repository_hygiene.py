# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
TRACKED = tuple(
    ROOT / name
    for name in subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--deduplicate", "-z"],
        cwd=ROOT,
        text=True,
    ).split("\0")
    if name and (ROOT / name).is_file()
)
SOURCES = tuple(
    path for path in TRACKED if path.suffix == ".py" and path.is_relative_to(ROOT / "src")
)


def test_sdist_ships_library_and_build_inputs_only() -> None:
    """The sdist promises a runnable test suite only if it ships one that can run.

    It cannot: a tarball has no `.git` for the license-header check above, no pinned
    interpreters for `fixtures/E-runtime`, and none of the cross-test imports the suite relies on.
    A shipped-but-untestable suite would be a second, weaker definition of
    "tests pass," so `only-include` carries what rebuilds the wheel (`src`, `schema` and the
    declared `README.md`) and distributors rebuild the test suite from the Git tag instead
    (docs/reference.md).
    """
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    only_include = config["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    missing = [entry for entry in only_include if not (ROOT / entry).exists()]
    assert missing == [], f"only-include names a path the repository does not have: {missing}"

    def is_test_input(entry: str) -> bool:
        return entry.partition("/")[0] in {"tests", "fixtures", "tools"}

    studio_build_inputs = {
        "tools/studio_ui.py",
        "tools/browser-runtime/package.json",
        "tools/browser-runtime/package-lock.json",
    }
    assert studio_build_inputs | {"studio"} <= set(only_include)
    shipped_test_inputs = [
        entry for entry in only_include if is_test_input(entry) and entry not in studio_build_inputs
    ]
    assert shipped_test_inputs == [], (
        "the sdist must not ship a test suite or its fixtures: it cannot run from a tarball "
        f"(see docs/reference.md), so shipping it half-working is worse than not shipping it; "
        f"found {shipped_test_inputs}"
    )
