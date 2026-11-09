# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-343: the replies of a source collector are frozen as golden data before its code is deleted.

Consumer: the recorder (`make golden-record`) and each phase that deletes a Python collector.
Set `ARCHKEEL_GOLDEN_PRODUCER=native` to compare the native binary instead of the Python collector.
"""

from __future__ import annotations

import copy
import gzip
import json
import os
import stat
import sys
import warnings
import zlib
from pathlib import Path
from typing import Any

import golden_producers
import golden_record
import golden_replies
import pytest

LANGUAGES = sorted(path.name for path in golden_replies.GOLDEN.iterdir() if path.is_dir())
CASES = [(lang, case) for lang in LANGUAGES for case in golden_record.cases(lang)]


class GoldenSubsetWarning(UserWarning):
    """The producer claims fewer sections than the golden reply, so the test compared a part."""


def _reply(sections: dict[str, list[dict[str, Any]]], claimed: list[str] | None = None) -> dict:
    return {
        "protocol_version": "3.0.0",
        "facts": {
            "adapter": {"name": "x", "version": "1", "code_digest": "d"},
            "runtime": {"name": "python", "version": "3.11"},
            "source": {"git_head": "a" * 40, "dirty": False, "source_digest": "s"},
            "capabilities": {"sections": claimed or list(sections)},
            "sections": [{"name": n, "records": r} for n, r in sections.items()],
            "files": [{"path": "/work/case/a.ts"}],
            "imports": [],
            "evidence": [],
            "inputs": [],
        },
    }


@pytest.mark.parametrize(("language", "case"), CASES, ids=[f"{lang}-{c}" for lang, c in CASES])
def test_the_producer_equals_the_golden_reply(
    language: str, case: str, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    name = os.environ.get(golden_producers.PRODUCER_VARIABLE, "python")
    binary = request.getfixturevalue("native_binary") if name == "native" else None
    run = golden_producers.producer(name, binary)
    root = golden_producers.materialize(golden_record.cases(language)[case], tmp_path)
    verdict = golden_replies.compare(
        golden_replies.load(language, case), golden_replies.canonical(run(root), root)
    )
    assert not verdict.mismatches, "\n".join(verdict.mismatches)
    assert verdict.compared, "the producer shares no section with the golden reply"
    if verdict.skipped:
        warnings.warn(
            f"{case}: compared {list(verdict.compared)}; NOT compared: {list(verdict.skipped)}",
            GoldenSubsetWarning,
            stacklevel=1,
        )


def test_every_golden_file_has_a_case_and_a_recording() -> None:
    for language in LANGUAGES:
        folder = golden_replies.GOLDEN / language
        names = set(golden_record.cases(language))
        files = {
            p.name.split(".")[0] for p in (*folder.glob("*.json.gz"), *folder.glob("*.digest.json"))
        }
        recorded = (folder / "RECORDINGS.md").read_text()
        assert files == names
        assert all(f"| {name} |" in recorded for name in names)


def test_the_golden_files_stay_small() -> None:
    total = sum(p.stat().st_size for p in golden_replies.GOLDEN.rglob("*.gz"))
    assert total <= 8 * golden_replies.FULL_REPLY_LIMIT
    assert not [
        p
        for p in golden_replies.GOLDEN.rglob("*.gz")
        if p.stat().st_size > golden_replies.FULL_REPLY_LIMIT
    ]


def test_the_canonical_form_drops_provenance_and_paths(tmp_path: Path) -> None:
    reply = _reply({"imports": [{"kind": "k", "title": f"{tmp_path}/a.ts"}]})
    reply["facts"]["files"] = [{"path": f"{tmp_path}/a.ts"}]
    value = golden_replies.canonical(reply, tmp_path)
    assert "protocol_version" not in value
    assert value["facts"]["adapter"] == {"name": "x"}
    assert value["facts"]["source"] == {"source_digest": "s"}
    assert value["facts"]["files"] == [{"path": "<root>/a.ts"}]
    assert "runtime" not in value["facts"]
    assert str(tmp_path) not in json.dumps(value)


@pytest.mark.parametrize("key", ["run_id", "elapsed_seconds", "duration_ms", "created_timestamp"])
def test_a_timing_or_run_id_cannot_be_a_golden_field(key: str, tmp_path: Path) -> None:
    reply = _reply({"imports": []})
    reply["facts"]["coverage"] = {key: 1}
    with pytest.raises(golden_replies.GoldenError, match=key):
        golden_replies.canonical(reply, tmp_path)


def test_a_small_reply_is_stored_in_full_and_a_large_one_as_a_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(golden_replies, "GOLDEN", tmp_path)
    value = _reply({"imports": [{"kind": "k"}, {"kind": "k"}, {"kind": "j"}]})
    assert golden_replies.store("lang", "one", value).name == "one.json.gz"
    assert golden_replies.load("lang", "one").full == value
    monkeypatch.setattr(golden_replies, "FULL_REPLY_LIMIT", 1)
    assert golden_replies.store("lang", "one", value).name == "one.digest.json"
    assert not (tmp_path / "lang" / "one.json.gz").exists()
    kept = golden_replies.load("lang", "one")
    assert kept.full is None
    assert kept.digest["sections"]["imports"]["kinds"] == {"j": 1, "k": 2}
    assert kept.digest["rest"]["counts"] == {"files": 1, "imports": 0, "evidence": 0, "inputs": 0}


@pytest.mark.parametrize("small", [True, False], ids=["full", "digest"])
def test_a_changed_record_fails_and_names_the_section(small: bool, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(golden_replies, "GOLDEN", tmp_path)
    monkeypatch.setattr(golden_replies, "FULL_REPLY_LIMIT", 10**6 if small else 1)
    value = _reply({"imports": [{"kind": "k", "title": "a"}], "calls": []})
    golden_replies.store("lang", "one", value)
    changed = copy.deepcopy(value)
    changed["facts"]["sections"][0]["records"][0]["title"] = "b"
    verdict = golden_replies.compare(golden_replies.load("lang", "one"), changed)
    assert len(verdict.mismatches) == 1 and verdict.mismatches[0].startswith("imports:")
    assert ("'a' != 'b'" in verdict.mismatches[0]) is small


def test_a_producer_with_fewer_sections_is_compared_on_its_sections_and_says_so() -> None:
    full = _reply({"imports": [{"kind": "k"}], "calls": [{"kind": "c"}]})
    native = _reply({"imports": [{"kind": "k"}]})
    golden = golden_replies.Golden(golden_replies.digest(full), full)
    verdict = golden_replies.compare(golden, native)
    assert verdict.mismatches == ()
    assert verdict.compared == ("imports",)
    assert verdict.skipped == ("calls", "files, imports, evidence")
    native["facts"]["sections"][0]["records"] = []
    assert golden_replies.compare(golden, native).mismatches
    claims_more = _reply({"imports": [], "calls": [], "bindings": []})
    assert "claims bindings" in golden_replies.compare(golden, claims_more).mismatches[0]


def test_the_recorder_refuses_without_a_reason(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(golden_replies, "GOLDEN", tmp_path)
    for reason in ("", "  "):
        with pytest.raises(golden_replies.GoldenError, match="REASON"):
            golden_record.record("typescript", ["h-typescript"], reason)
    assert list(tmp_path.iterdir()) == []


def test_the_native_producer_reads_a_compressed_reply(tmp_path: Path) -> None:
    root = golden_producers.materialize(
        golden_record.cases("typescript")["f-typescript-story"], tmp_path
    )
    expected = _reply({"imports": []})
    packed = tmp_path / "reply.bin"
    packed.write_bytes(zlib.compress(json.dumps(expected).encode()))
    fake = tmp_path / "fake-collector"
    fake.write_text(
        f"#!{sys.executable}\nimport sys\nsys.stdin.buffer.read()\n"
        f"sys.stdout.buffer.write(open({str(packed)!r}, 'rb').read())\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    assert golden_producers.producer("native", fake)(root) == expected
    with pytest.raises(ValueError, match="native producer without a binary"):
        golden_producers.producer("native")


def test_a_full_golden_file_is_canonical_gzip() -> None:
    path = next(golden_replies.GOLDEN.glob("typescript/*.json.gz"))
    raw = gzip.decompress(path.read_bytes())
    assert raw == golden_replies.canonical_bytes(json.loads(raw))
