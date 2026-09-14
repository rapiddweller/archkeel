# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from test_delta import _record
from test_expectation import _delta_payload, _expectation_payload, _typed_delta
from test_snapshot import _git, _write

import archkeel
from archkeel.check.expectation import ExpectationError, evaluate_expectation, parse_expectation
from archkeel.check.python_profile import crossing_imports
from archkeel.check.snapshot import SnapshotError, _materialize_archive, materialize_git_snapshot
from archkeel.ir.codec import parse_record


def test_package_digest_is_location_independent_and_covers_nested_source(tmp_path: Path) -> None:
    source = Path(archkeel.__file__).parent
    roots = [tmp_path / "first", tmp_path / "second"]
    for reverse, root in enumerate(roots):
        for path in sorted(source.rglob("*.py"), reverse=bool(reverse)):
            target = root / "archkeel" / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)

    def digest(root: Path) -> str:
        return subprocess.check_output(
            [
                sys.executable,
                "-B",
                "-S",
                "-c",
                "from archkeel.ir.digest import package_digest; print(package_digest())",
            ],
            cwd=root,
            text=True,
        ).strip()

    first = digest(roots[0])
    assert digest(roots[1]) == first
    path = roots[1] / "archkeel/check/python_profile.py"
    path.write_text(path.read_text() + "\n# changed checker source\n")
    assert digest(roots[1]) != first


@pytest.mark.parametrize("forged_expectation", [False, True])
def test_checker_digest_rejects_mismatched_or_jointly_forged_artifacts(
    forged_expectation: bool,
) -> None:
    delta = _delta_payload()
    payload = _expectation_payload()
    delta["provenance"]["checker_digest"] = "f" * 64
    if forged_expectation:
        payload["checker_digest"] = "f" * 64
    with pytest.raises(ExpectationError, match="checker_digest"):
        evaluate_expectation(_typed_delta(delta), parse_expectation(payload))


def test_expectation_requires_checker_digest() -> None:
    payload = _expectation_payload()
    del payload["checker_digest"]
    with pytest.raises(ExpectationError, match="checker_digest"):
        parse_expectation(payload)


@pytest.mark.parametrize(
    ("symbol", "source_package", "private_count", "api_count"),
    [
        ("_token", "app.tasks", 1, 1),
        ("token", "app.tasks", 0, 1),
        ("_token", "app.clients", 0, 0),
        (None, "app.tasks", 0, 0),
    ],
)
def test_python_profile_preserves_underscore_crossing_semantics(
    symbol: str | None, source_package: str, private_count: int, api_count: int
) -> None:
    imports = (
        parse_record(
            _record(
                "import",
                kind="import",
                data={
                    "symbol": symbol,
                    "source_package": source_package,
                    "target_package": "app.clients",
                },
            )
        ),
    )
    assert len(crossing_imports(imports, private=True)) == private_count
    assert len(crossing_imports(imports, private=False)) == api_count


@pytest.mark.parametrize(
    ("roots", "expected"),
    [
        (("src/app",), {"src/app/__init__.py", "src/app/core.py"}),
        (("src/app", "plugins"), {"src/app/__init__.py", "src/app/core.py", "plugins/extra.py"}),
        (
            (".",),
            {
                "src/app/__init__.py",
                "src/app/core.py",
                "src/application/other.py",
                "plugins/extra.py",
            },
        ),
    ],
)
def test_snapshot_uses_configured_roots_without_sibling_prefix_leakage(
    tmp_path: Path, roots: tuple[str, ...], expected: set[str]
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "archkeel@example.invalid")
    _git(tmp_path, "config", "user.name", "Archkeel Test")
    for name in (
        "src/app/__init__.py",
        "src/app/core.py",
        "src/application/other.py",
        "plugins/extra.py",
        "src/app/README.md",
    ):
        _write(tmp_path / name, "value = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "fixture")
    with materialize_git_snapshot(tmp_path, "HEAD", roots=roots) as snapshot:
        assert {
            path.relative_to(snapshot.root).as_posix() for path in snapshot.root.rglob("*.py")
        } == expected
    assert not snapshot.root.exists()


@pytest.mark.parametrize(
    "roots", [(), ("",), ("../outside",), ("/tmp",), ("a/../b",), ("a\\b",), ("*.py",), ("C:/a",)]
)
def test_snapshot_rejects_unsafe_configured_roots(tmp_path: Path, roots: tuple[str, ...]) -> None:
    with pytest.raises(SnapshotError):
        with materialize_git_snapshot(tmp_path, "HEAD", roots=roots):
            pytest.fail("unsafe scope accepted")


@pytest.mark.parametrize("names", [[], ["src/app/x.py", "src/app/x.py"], ["src/application/x.py"]])
def test_archive_rejects_empty_duplicate_and_out_of_scope_files(
    tmp_path: Path, names: list[str]
) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:") as archive:
        for name in names:
            member = tarfile.TarInfo(name)
            member.size = 1
            archive.addfile(member, io.BytesIO(b"1"))
    with pytest.raises(SnapshotError):
        _materialize_archive(buffer.getvalue(), tmp_path, roots=("src/app",))
