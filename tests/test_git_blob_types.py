# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One regular-blob grammar serves both immutable Git readers."""

import copy
import json
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members
from test_snapshot import _committed_repository, _git, _write
from test_uml_evaluation import _model

from archkeel.check import git, snapshot
from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
LEGACY = 'mode not in {b"100644", b"100755"} or kind != b"blob"'
NOMINAL = "regular_git_blob_kind(mode, kind) is None"
OWNERS = {
    "GIT-BLOB-TYPED-ARCHIVE": ("snapshot.py", "_git_archive_bytes"),
    "GIT-BLOB-TYPED-READER": ("git.py", "read_blob"),
}


def test_actual_git_blob_api_has_one_nominal_owner():
    assert hasattr(snapshot, "RegularGitBlobKind")
    assert hasattr(snapshot, "regular_git_blob_kind")
    assert issubclass(snapshot.RegularGitBlobKind, Enum)
    hints = get_type_hints(snapshot.regular_git_blob_kind)
    assert hints == {
        "mode": bytes,
        "kind": bytes,
        "return": snapshot.RegularGitBlobKind | None,
    }
    assert git.regular_git_blob_kind is snapshot.regular_git_blob_kind
    assert {item.value for item in snapshot.RegularGitBlobKind} == {
        (b"100644", b"blob"),
        (b"100755", b"blob"),
    }


@pytest.mark.parametrize(
    "mode,kind,member",
    [(b"100644", b"blob", "REGULAR"), (b"100755", b"blob", "EXECUTABLE")],
)
def test_regular_blob_pairs_return_the_canonical_member(mode, kind, member):
    assert snapshot.regular_git_blob_kind(mode, kind) is snapshot.RegularGitBlobKind[member]


@pytest.mark.parametrize(
    "mode,kind",
    [
        (b"120000", b"blob"),
        (b"160000", b"commit"),
        (b"040000", b"tree"),
        (b"100600", b"blob"),
        (b"0100644", b"blob"),
        (b"100644", b"commit"),
        (b"100755", b"tree"),
        (b"100644", b"future"),
        (b"", b"blob"),
        (b"100644", b""),
    ],
)
def test_other_git_metadata_is_not_a_supported_regular_blob(mode, kind):
    assert snapshot.regular_git_blob_kind(mode, kind) is None


def _authored_contract():
    contract = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/check.json").read_text())
    )
    contract.pop("$schema", None)
    root = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [r for r in root["rules"] if r["id"].startswith("GIT-BLOB-TYPED-")]
    assert len(contract["rules"]) == 3
    contract["declarations"]["modules"] = []
    uml = contract["declarations"]["uml"]
    uml["relationships"] = []
    uml["scopes"] = []
    uml["entities"] = [
        e for e in uml["entities"]
        if e["id"].startswith("GIT-BLOB-") or e["id"] == "SNAPSHOT-LANGUAGE-MODULE"
    ]
    assert len(uml["entities"]) == 3
    return contract


def _native_repository(tmp_path, *, raw_owner=None, weakening=None):
    contract = _authored_contract()
    files = {
        "archkeel/__init__.py": "",
        "archkeel/check/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/ir/facts.py": "from enum import StrEnum\n\n"
        + _source_members("src/archkeel/ir/facts.py", {"Language"}),
        "contract.json": json.dumps(contract),
    }
    for item in [
        *contract["components"], *contract["rules"],
        *contract["declarations"]["uml"]["entities"],
    ]:
        for path in item["provenance"]:
            files[path] = (ROOT / path).read_text()
    for filename in ("git.py", "snapshot.py"):
        source = (ROOT / "src/archkeel/check" / filename).read_text()
        if raw_owner is not None and filename == OWNERS[raw_owner][0]:
            if NOMINAL in source:
                source = source.replace(NOMINAL, LEGACY, 1)
            else:
                assert LEGACY in source
        if filename == "snapshot.py" and weakening is not None:
            old, new = weakening
            assert old in source
            source = source.replace(old, new, 1)
        files["archkeel/check/" + filename] = source
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_actual_git_blob_target_and_scoped_guards_pass(tmp_path):
    root, config = _native_repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    guards = [
        r for r in rule_assessments(model, undecided_by_rule={})
        if r.id.startswith("GIT-BLOB-TYPED-")
    ]
    assert len(guards) == 3
    assert all(r.status == "PASS" and r.evaluation_proven for r in guards), guards
    assert not trace_valid_violations(model)


@pytest.mark.parametrize("guard", OWNERS)
def test_actual_byte_comparisons_fail_the_unchanged_native_guard(tmp_path, guard):
    root, config = _native_repository(tmp_path, raw_owner=guard)
    intent = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assessment = next(
        r for r in rule_assessments(model, undecided_by_rule={}) if r.id == guard
    )
    assert assessment.status == "FAIL" and assessment.evaluation_proven, assessment
    violations = [r for r in trace_valid_violations(model) if guard in r.rule_ids]
    assert violations
    assert all(r.data.get("owner") == "archkeel.check." + ".".join(
        (OWNERS[guard][0][:-3], OWNERS[guard][1])
    ) for r in violations), violations
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    "weakening",
    [
        ("mode: bytes, kind: bytes", "mode: object, kind: bytes"),
        ("mode: bytes, kind: bytes", "mode: bytes, kind: object"),
        (") -> RegularGitBlobKind | None:", ") -> str | None:"),
    ],
)
def test_git_blob_target_rejects_actual_input_and_return_weakening(tmp_path, weakening):
    root, config = _native_repository(tmp_path, weakening=weakening)
    intent = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None
    assert any(
        r.subject_id == "GIT-BLOB-PARSER" and r.aspect == "signature" and r.status == "FAIL"
        for r in comparison.assessments
    ), comparison
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize("executable", [False, True])
def test_both_readers_keep_exact_real_git_payloads(tmp_path, executable):
    root, _ = _committed_repository(tmp_path)
    payload = b"print('exact')\r\n# \xc3\xa4\n"
    path = "example/tasks/sample.py"
    (root / path).write_bytes(payload)
    _git(root, "add", path)
    _git(root, "update-index", "--chmod=" + ("+x" if executable else "-x"), path)
    _git(root, "commit", "-qm", "regular blob modes")
    revision = _git(root, "rev-parse", "HEAD")
    assert git.read_blob(root, revision, path) == payload
    with snapshot.materialize_git_snapshot(root, revision, roots=("example",)) as archived:
        assert (archived.root / path).read_bytes() == payload


@pytest.mark.parametrize("mode", ["120000", "160000"])
def test_both_readers_reject_selected_nonregular_git_objects_with_legacy_errors(tmp_path, mode):
    root, revision = _committed_repository(tmp_path)
    path = "example/selected.py"
    if mode == "120000":
        _write(root / path, "target")
        _git(root, "add", path)
        oid = _git(root, "rev-parse", ":example/selected.py")
    else:
        oid = revision
    _git(root, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}")
    _git(root, "commit", "-qm", "nonregular selected object")
    revision = _git(root, "rev-parse", "HEAD")
    with pytest.raises(git.GitError) as direct:
        git.read_blob(root, revision, path)
    assert type(direct.value) is git.GitError
    assert str(direct.value) == "expected a regular Git blob: " + path
    with pytest.raises(snapshot.SnapshotError) as archive:
        snapshot._git_archive_bytes(
            root, revision, roots=(PurePosixPath("example"),),
        )
    assert str(archive.value) == f"expected a regular Git blob: {path!r}"


def test_unselected_nonregular_object_and_missing_blob_keep_legacy_behavior(tmp_path):
    root, _ = _committed_repository(tmp_path)
    _write(root / "outside/link.py", "target")
    _git(root, "add", "outside/link.py")
    oid = _git(root, "rev-parse", ":outside/link.py")
    _git(root, "update-index", "--cacheinfo", f"120000,{oid},outside/link.py")
    _git(root, "commit", "-qm", "unselected symlink")
    revision = _git(root, "rev-parse", "HEAD")
    with snapshot.materialize_git_snapshot(root, revision, roots=("example",)) as archived:
        assert not (archived.root / "outside/link.py").exists()
    with pytest.raises(git.MissingBlobError) as missing:
        git.read_blob(root, revision, "absent.py")
    assert str(missing.value) == "missing regular Git blob: absent.py"
