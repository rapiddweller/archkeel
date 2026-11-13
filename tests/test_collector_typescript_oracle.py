# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The migration oracle rejects missing keys, changed bytes and undeclared source roots."""

import hashlib
import json
import zlib
from pathlib import Path
from zipfile import ZipFile

import pytest
import recorded_typescript as oracle

from tools import record_typescript_calls as recorder


def _snapshot(directory, **changes):
    with ZipFile(directory / "public.zip", "w"):
        pass
    header = {
        "archive": "public.zip",
        "main_sha": "a" * 40,
        "tests": {},
        "content_digest": hashlib.sha256((directory / "public.zip").read_bytes()).hexdigest(),
    }
    header.update(changes)
    (directory / "manifest.json").write_text(json.dumps(header))


@pytest.mark.parametrize(
    "node",
    [
        "tests/test_example.py::test_case[x@y] (call)",
        "tests/test_example.py::test_case[x@y]@test_example.py (call)",
    ],
)
def test_xdist_group_is_not_a_recorded_key(node):
    assert oracle.call_id(node) == "tests/test_example.py::test_case[x@y]"


@pytest.mark.parametrize("phase", ["", " (setup)", " (call)", " (teardown)"])
def test_parentheses_in_parameter_ids_are_not_phase_metadata(phase):
    node = "tests/test_example.py::test_case[function () {}]"
    assert oracle.call_id(node + phase) == node


def test_a_missing_recorded_key_has_a_named_assertion(tmp_path, monkeypatch):
    _snapshot(tmp_path)
    monkeypatch.setattr(oracle, "DIRECTORY", tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_missing.py::test_missing (setup)")
    monkeypatch.delenv(recorder.ENV, raising=False)
    with pytest.raises(AssertionError, match="typescript_oracle_missing_key"):
        oracle.read("collect", None)


def test_snapshot_header_checks_the_content_digest(tmp_path):
    _snapshot(tmp_path, content_digest="0" * 64)
    with pytest.raises(AssertionError, match="typescript_oracle_content_digest_mismatch"):
        oracle.main_calls(tmp_path)


@pytest.mark.parametrize("compressed", [False, True])
def test_grouped_recording_preserves_the_exact_wire_bytes(tmp_path, monkeypatch, compressed):
    data = b'{"value":"public fixture"}'
    wire = zlib.compress(data, level=1) if compressed else data
    test = "tests/test_example.py::test_wire"
    member = json.dumps({"collect": [recorder.pack_reply(wire)]}).encode()
    _snapshot(tmp_path)
    with ZipFile(tmp_path / "public.zip", "w") as archive:
        archive.writestr("wire.json", member)
    header = json.loads((tmp_path / "manifest.json").read_bytes())
    header["content_digest"] = hashlib.sha256((tmp_path / "public.zip").read_bytes()).hexdigest()
    header["tests"] = {
        test: {
            "sources": ["repository"],
            "file": "wire.json",
            "sha256": hashlib.sha256(member).hexdigest(),
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(header))
    monkeypatch.setattr(oracle, "DIRECTORY", tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", test + " (call)")
    monkeypatch.delenv(recorder.ENV, raising=False)
    monkeypatch.setitem(oracle.COUNTS, (test, "collect"), 0)
    assert oracle.read("collect") == wire


def test_recording_outside_a_declared_public_root_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "ROOT", tmp_path / "checkout")
    monkeypatch.delenv("ARCHKEEL_PUBLIC_EXCALIDRAW", raising=False)
    with pytest.raises(AssertionError, match="typescript_oracle_source_outside_public_roots"):
        recorder.source_name(tmp_path / "outside")


@pytest.mark.parametrize("damage", ["origin", "local", "dirty"])
def test_public_input_requires_the_named_origin_and_a_clean_tree(tmp_path, monkeypatch, damage):
    def git(root, *args):
        if args[0] == "remote":
            if damage == "local":
                return "github.com/excalidraw/excalidraw"
            return (
                "https://example.invalid/unlisted"
                if damage == "origin"
                else ("https://github.com/excalidraw/excalidraw.git")
            )
        return " M source.ts" if damage == "dirty" else ""

    monkeypatch.setattr(recorder, "_git", git)
    monkeypatch.setattr(recorder, "ROOT", tmp_path / "checkout")
    monkeypatch.setenv("ARCHKEEL_PUBLIC_EXCALIDRAW", str(tmp_path / "public"))
    with pytest.raises(AssertionError, match="typescript_oracle_public_"):
        recorder.source_name(tmp_path / "public/src.ts")


def test_a_source_symlink_cannot_escape_the_checkout(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "escape").symlink_to(tmp_path / "outside")
    monkeypatch.setattr(recorder, "ROOT", checkout)
    monkeypatch.delenv("ARCHKEEL_PUBLIC_EXCALIDRAW", raising=False)
    with pytest.raises(AssertionError, match="typescript_oracle_source_outside_public_roots"):
        recorder.source_name(checkout / "escape")


def test_recorded_source_roots_are_checked_before_replay(tmp_path):
    _snapshot(tmp_path, tests={"case": {"sources": ["/outside"]}})
    with pytest.raises(AssertionError, match="typescript_oracle_source_outside_public_roots"):
        oracle.main_calls(tmp_path)


@pytest.mark.parametrize("through_directory", [False, True])
def test_a_nested_source_symlink_is_refused_before_collection(
    tmp_path, monkeypatch, through_directory
):
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    outside = tmp_path / "outside.ts"
    outside.write_text("export {}")
    directory = checkout / "src"
    if through_directory:
        directory = checkout / "test-artifacts/cache"
        directory.mkdir(parents=True)
        (checkout / "src/dependency").symlink_to(directory, target_is_directory=True)
    (directory / "escape.ts").symlink_to(outside)
    monkeypatch.setattr(recorder, "ROOT", checkout)
    monkeypatch.delenv("ARCHKEEL_PUBLIC_EXCALIDRAW", raising=False)
    with pytest.raises(AssertionError, match="typescript_oracle_source_outside_public_roots"):
        recorder.source_tree(checkout)


def test_committed_recordings_only_name_public_source_roots():
    snapshot = oracle.main_calls(oracle.DIRECTORY)
    assert snapshot["tests"]
    members = [entry["file"] for entry in snapshot["tests"].values()]
    assert len(members) == len(set(members))
    with ZipFile(oracle.DIRECTORY / snapshot["archive"]) as archive:
        assert sorted(archive.namelist()) == sorted(members)


def test_internal_directory_link_cycles_do_not_repeat_the_source_walk(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/self").symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / "src/loop.ts").symlink_to("loop.ts")
    monkeypatch.setattr(recorder, "ROOT", tmp_path)
    assert recorder.source_tree(tmp_path) == "repository"


def test_studio_comparison_skips_visibly_without_its_dependency(tmp_path, monkeypatch):
    import test_collector_native_imports as imports

    monkeypatch.setattr(imports, "ROOT", tmp_path)
    with pytest.raises(pytest.skip.Exception, match="make browser-runtime-install"):
        imports._request(tmp_path, "archkeel.studio.ui", "tsconfig.json")


def test_parser_probe_sources_are_public_tests_and_relative_files():
    import gzip

    from tools.record_typescript_parser import FILES

    data = json.loads(
        gzip.decompress((oracle.DIRECTORY.parent / "typescript_legacy_parser.json.gz").read_bytes())
    )
    content = json.dumps(data["cases"], sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(content).hexdigest() == data["content_digest"]
    assert len(data["main_sha"]) == 40
    assert set(data["public_tests"]) == set(FILES)
    assert all(test.split("::", 1)[0] in FILES for test in data["cases"])
    assert all(
        not Path(case["rel"]).is_absolute() and ".." not in Path(case["rel"]).parts
        for cases in data["cases"].values()
        for case in cases
    )
