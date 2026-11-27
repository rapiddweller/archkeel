# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A cached checkout of a pinned source is used only when its bytes are the pinned commit (#659).

The folder name and `HEAD` prove nothing. Each test uses a local repository as the project: no
network. A refused cache stays as it is: it is not repaired, deleted or fetched again.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from test_report_gallery_sources import _git, _upstream

from tools import fixture_source, fixture_tree
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
    folders = sorted(path.name for path in cache.iterdir() if path.name != "CACHEDIR.TAG")
    assert folders == [results[0].name], "one folder, no leftover"
    verify_checkout(results[0], spec["commit"])


# The type and the mode of a file are part of the pin (#659, second review of PR #1838).
def _tree(tmp_path: Path, files: dict[str, str], links: dict[str, str]) -> dict:
    """A local repository with files, links and an executable; the spec that pins its commit."""
    repo = tmp_path / "linked"
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    for name, target in links.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).symlink_to(target)
    (repo / "pkg").mkdir(parents=True, exist_ok=True)
    (repo / "pkg" / "run.sh").write_text("#!/bin/sh\n")
    (repo / "pkg" / "run.sh").chmod(0o755)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "one")
    return {
        "name": "Linked",
        "repo": str(repo),
        "ref": None,
        "commit": _git(repo, "rev-parse", "HEAD"),
        "license": "MIT",
        "copy": [{"from": "pkg", "to": "pkg"}],
    }


def _linked(tmp_path: Path) -> tuple[dict, Path]:
    spec = _tree(tmp_path, {"pkg/b.py": "y = 2\n"}, {"pkg/a.py": "b.py"})
    with checkout(spec, tmp_path / "cache") as ready:
        return spec, ready


def test_the_pinned_link_and_the_executable_are_copied_as_they_are_and_committed(
    tmp_path: Path,
) -> None:
    spec, _ = _linked(tmp_path)
    fixture = tmp_path / "fx"
    fixture.mkdir()
    (fixture / "SOURCE.json").write_text(json.dumps(spec))
    with fixture_tree.fixture_tree(fixture, None, tmp_path / "cache") as tree:
        assert (tree / "pkg" / "a.py").is_symlink()
        assert os.readlink(tree / "pkg" / "a.py") == "b.py"
        assert os.access(tree / "pkg" / "run.sh", os.X_OK)
        staged = _git(tree, "ls-files", "-s", "pkg").splitlines()
    assert {line.split()[0] for line in staged} == {"120000", "100644", "100755"}


def _swap(path: Path, make: Callable[[Path], object]) -> None:
    path.unlink()
    make(path)


@pytest.mark.parametrize(
    "swap",
    [
        lambda root: _swap(root / "pkg" / "a.py", lambda path: path.write_text("b.py")),
        lambda root: _swap(root / "pkg" / "b.py", lambda path: path.symlink_to("y = 2\n")),
        lambda root: _swap(root / "pkg" / "a.py", lambda path: path.symlink_to("c.py")),
    ],
    ids=[
        "link-became-file-with-the-target-bytes",
        "file-became-link-with-its-bytes",
        "link-retargeted",
    ],
)
def test_the_same_bytes_in_another_type_or_another_link_target_are_refused(
    tmp_path: Path, swap: Callable[[Path], object]
) -> None:
    spec, ready = _linked(tmp_path)
    swap(ready)
    with pytest.raises(SourceError, match="1 changed in bytes, type or mode"):
        verify_checkout(ready, spec["commit"])


def test_a_link_to_a_folder_replaced_by_the_folder_is_refused(tmp_path: Path) -> None:
    spec = _tree(tmp_path, {"pkg/real/c.py": "z = 3\n"}, {"pkg/d": "real"})
    with checkout(spec, tmp_path / "cache") as ready:
        (ready / "pkg" / "d").unlink()
        shutil.copytree(ready / "pkg" / "real", ready / "pkg" / "d")
        with pytest.raises(SourceError, match="differs from the pinned commit"):
            verify_checkout(ready, spec["commit"])


@pytest.mark.skipif(os.name != "posix", reason="the executable bit needs a POSIX file system")
def test_the_executable_bit_is_part_of_the_pin_where_the_checkout_records_it(
    tmp_path: Path,
) -> None:
    spec, ready = _linked(tmp_path)
    script = ready / "pkg" / "run.sh"
    script.chmod(0o644)
    with pytest.raises(SourceError, match="1 changed in bytes, type or mode"):
        verify_checkout(ready, spec["commit"])
    script.chmod(0o755)
    (ready / "pkg" / "b.py").chmod(0o755)
    with pytest.raises(SourceError, match="1 changed in bytes, type or mode"):
        verify_checkout(ready, spec["commit"])
    # A file system without the bit: the checkout says so, and the bit is not claimed.
    _git(ready, "config", "core.filemode", "false")
    verify_checkout(ready, spec["commit"])


def test_a_link_that_leaves_the_fixture_is_not_copied(tmp_path: Path) -> None:
    for name, target in {"out": "../../../outside.txt", "absolute": "/etc/hosts"}.items():
        spec = _tree(tmp_path / name, {"pkg/b.py": "y = 2\n"}, {f"pkg/{name}": target})
        root = tmp_path / f"root-{name}"
        root.mkdir()
        with checkout(spec, tmp_path / f"cache-{name}") as ready:
            with pytest.raises(SourceError, match="leaves the source"):
                fixture_source.copy_source(ready, spec, root)


def test_a_copied_path_that_is_a_link_to_another_folder_is_refused(tmp_path: Path) -> None:
    spec = _tree(tmp_path, {"elsewhere/c.py": "z = 3\n"}, {"pkg/inner": "../elsewhere"})
    outer = {**spec, "copy": [{"from": "pkg/inner", "to": "inner"}]}
    root = tmp_path / "root"
    root.mkdir()
    with checkout(spec, tmp_path / "cache") as ready:
        with pytest.raises(SourceError, match="is or goes through a link"):
            fixture_source.copy_source(ready, outer, root)
    assert not (root / "inner").exists()


def test_the_shape_of_the_dart_pin_copies_its_link_and_keeps_it_inside(tmp_path: Path) -> None:
    """`pkgs/bazel_worker/e2e_test/analysis_options.yaml -> ../analysis_options.yaml`."""
    spec = _tree(
        tmp_path,
        {"pkgs/bazel_worker/analysis_options.yaml": "linter: {}\n"},
        {"pkgs/bazel_worker/e2e_test/analysis_options.yaml": "../analysis_options.yaml"},
    )
    dart = {**spec, "copy": [{"from": "pkgs/bazel_worker", "to": ".", "exclude": ["test"]}]}
    root = tmp_path / "root"
    root.mkdir()
    with checkout(dart, tmp_path / "cache") as ready:
        fixture_source.copy_source(ready, dart, root)
        link = root / "e2e_test" / "analysis_options.yaml"
        assert link.is_symlink() and os.readlink(link) == "../analysis_options.yaml"
        assert link.resolve() == (root / "analysis_options.yaml").resolve()
        link.unlink()
        (ready / "pkgs/bazel_worker/e2e_test/analysis_options.yaml").unlink()
        (ready / "pkgs/bazel_worker/e2e_test/analysis_options.yaml").write_text(
            "../analysis_options.yaml"
        )
        with pytest.raises(SourceError, match="1 changed in bytes, type or mode"):
            verify_checkout(ready, dart["commit"])


@pytest.mark.skipif(
    not os.environ.get("ARCHKEEL_FETCH_SOURCES"), reason="the real pin needs the network"
)
def test_the_real_dart_pin_verifies_and_copies_its_one_link_inside_the_fixture(
    tmp_path: Path,
) -> None:
    folder = Path(__file__).resolve().parents[1] / "fixtures" / "O-bazel-worker-realworld"
    spec = fixture_source.load(folder)
    root = tmp_path / "root"
    root.mkdir()
    with checkout(spec, tmp_path / "cache") as ready:
        verify_checkout(ready, spec["commit"])
        fixture_source.copy_source(ready, spec, root)
        link = root / "e2e_test" / "analysis_options.yaml"
        assert link.is_symlink() and os.readlink(link) == "../analysis_options.yaml"
        assert link.resolve().is_relative_to(root.resolve())
        # Replace the link by a file with the bytes of its target: the pin refuses it.
        original = ready / "pkgs" / "bazel_worker" / "e2e_test" / "analysis_options.yaml"
        original.unlink()
        original.write_text("../analysis_options.yaml")
        with pytest.raises(SourceError, match="1 changed in bytes, type or mode"):
            verify_checkout(ready, spec["commit"])
