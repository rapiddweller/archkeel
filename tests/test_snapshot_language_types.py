# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Revision snapshots consume the existing canonical language port."""

import copy
import json
from pathlib import Path, PurePosixPath
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_snapshot import _committed_repository, _git, _write

from archkeel.check import snapshot
from archkeel.check.ports import ScanConfig
from archkeel.ir.facts import Language

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "entry",
    [snapshot.materialize_git_snapshot, snapshot._git_archive_bytes, snapshot._materialize_archive],
)
def test_snapshot_language_ports_use_the_one_facts_type(entry):
    assert get_type_hints(entry)["language"] is Language


@pytest.mark.parametrize(
    "language,source,metadata",
    [
        (Language.PYTHON, "example/main.py", "pyproject.toml"),
        (Language.DART, "example/main.dart", "pubspec.yaml"),
        (Language.TYPESCRIPT, "example/main.ts", "tsconfig.json"),
    ],
)
def test_snapshot_enum_and_legacy_ingress_preserve_exact_committed_files(
    tmp_path, language, source, metadata
):
    root, _ = _committed_repository(tmp_path)
    _write(root / source, "selected\r\n")
    _write(root / metadata, "metadata\r\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "language fixture")
    revision = _git(root, "rev-parse", "HEAD")
    snapshots = []
    for value in (language, language.value):
        archive = snapshot._git_archive_bytes(
            root, revision, roots=(PurePosixPath("example"),), language=value
        )
        destination = tmp_path / ("enum" if isinstance(value, Language) else "legacy")
        snapshot._materialize_archive(archive, destination, roots=("example",), language=value)
        snapshots.append(
            {
                path.relative_to(destination).as_posix(): path.read_bytes()
                for path in destination.rglob("*")
                if path.is_file()
            }
        )
    assert snapshots[0] == snapshots[1]
    assert snapshots[0][source] == b"selected\r\n"
    assert snapshots[0][metadata] == b"metadata\r\n"


@pytest.mark.parametrize("language", ["", "Python", "future"])
@pytest.mark.parametrize("archive", [False, True])
def test_unsupported_snapshot_language_keeps_exact_error_before_reading(
    tmp_path, language, archive
):
    with pytest.raises(snapshot.SnapshotError) as error:
        if archive:
            snapshot._materialize_archive(b"not a tar", tmp_path, roots=(), language=language)
        else:
            snapshot._git_archive_bytes(tmp_path, "0" * 40, roots=(), language=language)
    assert type(error.value) is snapshot.SnapshotError
    assert str(error.value) == f"unsupported snapshot language: {language}"


@pytest.mark.parametrize("bad_roots", [False, True])
def test_public_snapshot_validation_order_precedes_language_rejection(tmp_path, bad_roots):
    root, _ = _committed_repository(tmp_path)
    with pytest.raises(snapshot.SnapshotError) as error:
        with snapshot.materialize_git_snapshot(
            root, "missing", roots=() if bad_roots else ("example",), language="future"
        ):
            pass
    assert str(error.value) == (
        "snapshot roots must not be empty" if bad_roots else "cannot resolve Git revision 'missing'"
    )


def _target_repository(tmp_path):
    contract = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/check.json").read_text())
    )
    contract.pop("$schema", None)
    contract["rules"] = []
    contract["declarations"]["modules"] = []
    uml = contract["declarations"]["uml"]
    uml["relationships"] = []
    uml["scopes"] = []
    uml["entities"] = [
        item for item in uml["entities"] if item["id"].startswith("SNAPSHOT-LANGUAGE-")
    ]
    assert len(uml["entities"]) == 4
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/check/__init__.py": "",
            "archkeel/check/snapshot.py": (ROOT / "src/archkeel/check/snapshot.py").read_text(),
            "contract.json": json.dumps(contract),
            "docs/superpowers/plans/2026-10-17-snapshot-language.md": "Language ingress.\n",
        },
    )
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)
