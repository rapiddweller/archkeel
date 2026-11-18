# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A cached checkout of a pinned source is used only when its bytes are the pinned commit (#659).

The folder name and `HEAD` prove nothing. Each test uses a local repository as the project: no
network. A refused cache stays as it is: it is not repaired, deleted or fetched again.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from test_report_gallery_sources import _git, _upstream

from tools import fixture_source
from tools.fixture_source import SourceError, checkout, verify_checkout


def _cached(tmp_path: Path) -> tuple[dict, Path, Path]:
    """The spec, the cache folder and the checkout that a first build left in it."""
    spec = _upstream(tmp_path)
    cache = tmp_path / "cache"
    with checkout(spec, cache) as ready:
        return spec, cache, ready


def _files(folder: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()}


def test_a_verified_cache_serves_the_next_build_offline_and_again(tmp_path: Path) -> None:
    spec, cache, ready = _cached(tmp_path)
    (tmp_path / "upstream").rename(tmp_path / "gone")
    for number in range(2):
        with checkout(spec, cache) as again:
            assert again == ready
            root = tmp_path / f"copy-{number}"
            root.mkdir()
            fixture_source.copy_source(again, spec, root)
        assert (root / "pkg" / "a.py").read_text() == "x = 1\n"
        assert not (root / "pkg" / "skip.py").exists()


def test_a_folder_with_the_right_name_and_wrong_source_and_no_git_is_refused(
    tmp_path: Path,
) -> None:
    spec, cache, ready = _cached(tmp_path)
    shutil.rmtree(ready)
    (ready / "pkg").mkdir(parents=True)
    (ready / "pkg" / "__init__.py").write_text("# wrong source\n")
    with pytest.raises(SourceError, match="no folder .git"), checkout(spec, cache):
        pass
    assert (ready / "pkg" / "__init__.py").read_text() == "# wrong source\n", "not deleted"


def test_a_checkout_at_another_commit_under_the_name_of_the_pin_is_refused(
    tmp_path: Path,
) -> None:
    spec, cache, ready = _cached(tmp_path)
    upstream = tmp_path / "upstream"
    (upstream / "pkg" / "a.py").write_text("x = 99\n")
    _git(upstream, "commit", "-qam", "two")
    other = {**spec, "commit": _git(upstream, "rev-parse", "HEAD")}
    shutil.rmtree(ready)
    with checkout(other, cache) as moved:
        moved.rename(ready)  # the name of the pin, the content of another commit
    with pytest.raises(SourceError, match="the pin is"), checkout(spec, cache):
        pass
    assert (ready / "pkg" / "a.py").read_text() == "x = 99\n"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda root: (root / "pkg" / "a.py").write_text("x = 2\n"), "1 changed"),
        (lambda root: (root / "pkg" / "extra.py").write_text("q = 1\n"), "1 added or missing"),
        (lambda root: (root / "pkg" / "sub" / "b.py").unlink(), "1 added or missing"),
        (lambda root: (root / "outside.js").write_text("const v = 42;\n"), "1 added or missing"),
        (lambda root: (root / ".gitignore").write_text("*.py\n"), "1 added or missing"),
    ],
    ids=["modified", "untracked", "deleted", "outside", "ignore-file"],
)
def test_a_cached_checkout_with_a_changed_working_file_is_refused(
    tmp_path: Path, change: Callable[[Path], object], message: str
) -> None:
    spec, cache, ready = _cached(tmp_path)
    change(ready)
    before = _files(ready)
    with pytest.raises(SourceError, match=message), checkout(spec, cache):
        pass
    assert _files(ready) == before, "the refused cache is not touched"


def test_a_modified_file_with_the_size_and_time_of_the_original_is_still_refused(
    tmp_path: Path,
) -> None:
    spec, cache, ready = _cached(tmp_path)
    target = ready / "pkg" / "a.py"
    stat = target.stat()
    target.write_text("x = 2\n")  # the same size
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(SourceError, match="1 changed"), checkout(spec, cache):
        pass


def test_a_damaged_object_store_is_refused(tmp_path: Path) -> None:
    spec, cache, ready = _cached(tmp_path)
    objects = ready / ".git" / "objects"
    stored = sorted(
        path for path in objects.rglob("*") if path.is_file() and path.parent.name != "info"
    )
    victim = stored[0]
    victim.chmod(0o644)
    data = bytearray(victim.read_bytes())
    data[len(data) // 2] ^= 0xFF
    victim.write_bytes(bytes(data))
    with pytest.raises(SourceError, match="git fsck"), checkout(spec, cache):
        pass


def test_borrowed_objects_are_refused(tmp_path: Path) -> None:
    spec, cache, ready = _cached(tmp_path)
    (ready / ".git" / "objects" / "info").mkdir(exist_ok=True)
    (ready / ".git" / "objects" / "info" / "alternates").write_text(str(tmp_path) + "\n")
    with pytest.raises(SourceError, match="borrows objects"), checkout(spec, cache):
        pass


def test_a_replacement_ref_does_not_change_what_is_verified(tmp_path: Path) -> None:
    spec, _, ready = _cached(tmp_path)
    blob = _git(ready, "rev-parse", "HEAD:pkg/a.py")
    forged = (
        subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=ready,
            input=b"x = 666\n",
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    _git(ready, "replace", blob, forged)
    assert _git(ready, "cat-file", "blob", blob) == "x = 666", "the replacement is in effect"
    verify_checkout(ready, spec["commit"])  # the real blob decides
    (ready / "pkg" / "a.py").write_text("x = 666\n")  # what a replacement-aware reader would accept
    with pytest.raises(SourceError, match="1 changed"):
        verify_checkout(ready, spec["commit"])


def test_two_builds_that_fetch_the_same_pin_at_once_leave_one_clean_checkout(
    tmp_path: Path,
) -> None:
    spec = _upstream(tmp_path)
    cache = tmp_path / "cache"
    results: list[Path | BaseException] = []

    def build() -> None:
        try:
            with checkout(spec, cache) as ready:
                results.append(ready)
        except BaseException as error:  # noqa: BLE001 - the test reports it
            results.append(error)

    threads = [threading.Thread(target=build) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(isinstance(result, Path) for result in results), results
    assert [path.name for path in cache.iterdir()] == [results[0].name], "one folder, no leftover"
    verify_checkout(results[0], spec["commit"])
