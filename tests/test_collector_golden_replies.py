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
    """The test compared a part of the reply: an allowance, or another interpreter than the pin."""


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
            "type_shapes": [],
            "uncertain_reexports": [],
            "candidate_evidence": [],
        },
    }


@pytest.mark.parametrize(("language", "case"), CASES, ids=[f"{lang}-{c}" for lang, c in CASES])
def test_the_producer_equals_the_golden_reply(
    language: str, case: str, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    name = os.environ.get(golden_producers.PRODUCER_VARIABLE, "python")
    if name == "native" and language != "typescript":
        pytest.skip("the native producer reads TypeScript only")
    binary = request.getfixturevalue("native_binary") if name == "native" else None
    options = golden_record.options(language, case)
    run = golden_producers.producer(name, binary, language=language, **options)
    pin = golden_replies.pin_for(language)
    golden_replies.require_recorded_interpreter(pin, os.environ)
    root = golden_producers.materialize(golden_record.cases(language)[case], tmp_path)
    verdict = golden_replies.compare_on_interpreter(
        golden_replies.load(language, case),
        golden_replies.canonical(run(root), root),
        golden_replies.allowance_for(language, os.environ),
        pin,
    )
    assert not verdict.mismatches, "\n".join(verdict.mismatches)
    assert verdict.compared, "the producer shares no section with the golden reply"
    if verdict.unpinned:
        warnings.warn(f"{case}: {verdict.unpinned}", GoldenSubsetWarning, stacklevel=1)
    if verdict.skipped:
        warnings.warn(
            f"{case}: NOT compared: sections {list(verdict.skipped)}. Allowance: {verdict.reason}",
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
    assert kept.digest["rest"]["counts"] == {
        "files": 1,
        "imports": 0,
        "evidence": 0,
        "inputs": 0,
        "type_shapes": 0,
        "uncertain_reexports": 0,
        "candidate_evidence": 0,
    }


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


def _golden(**sections: list[dict[str, Any]]) -> tuple[golden_replies.Golden, dict]:
    value = _reply(sections)
    return golden_replies.Golden(golden_replies.digest(value), value), value


ALLOW_CALLS = golden_replies.Allowance(("calls",), "The native collector has no calls yet.")


def test_a_swapped_section_order_fails() -> None:
    golden, value = _golden(imports=[{"kind": "k"}], calls=[{"kind": "c"}])
    swapped = copy.deepcopy(value)
    swapped["facts"]["sections"].reverse()
    assert "section order" in golden_replies.compare(golden, swapped).mismatches[0]


def test_an_extra_unclaimed_section_fails() -> None:
    golden, value = _golden(imports=[{"kind": "k"}])
    extra = copy.deepcopy(value)
    extra["facts"]["sections"].append({"name": "calls", "records": []})
    assert golden_replies.compare(golden, extra).mismatches


def test_a_duplicate_section_name_is_an_error_in_either_reply() -> None:
    golden, value = _golden(imports=[{"kind": "k"}])
    twice = copy.deepcopy(value)
    twice["facts"]["sections"].append({"name": "imports", "records": [{"kind": "bad"}]})
    with pytest.raises(golden_replies.GoldenError, match="duplicate section"):
        golden_replies.compare(golden, twice)
    with pytest.raises(golden_replies.GoldenError, match="duplicate section"):
        golden_replies.digest(twice)


def test_a_field_that_only_the_whole_reply_digest_covers_fails() -> None:
    golden, value = _golden(imports=[{"kind": "k"}], calls=[])
    changed = copy.deepcopy(value)
    changed["facts"]["capabilities"]["sections"].reverse()
    assert "whole reply" in golden_replies.compare(golden, changed).mismatches[0]


def test_an_empty_provider_bindings_list_is_the_same_as_no_key() -> None:
    """Protocol 4.0.0 and later write the key; the golden replies were recorded at 3.0.0."""
    _, value = _golden(imports=[{"kind": "k"}])
    newer = copy.deepcopy(value)
    newer["facts"]["provider_bindings"] = []
    assert golden_replies.digest(newer)["rest"] == golden_replies.digest(value)["rest"]
    filled = copy.deepcopy(value)
    filled["facts"]["provider_bindings"] = [{"name": "x"}]
    assert golden_replies.digest(filled)["rest"] != golden_replies.digest(value)["rest"]


def test_a_subset_fails_without_an_allowance() -> None:
    golden, value = _golden(imports=[{"kind": "k"}], calls=[{"kind": "c"}])
    native = _reply({"imports": [{"kind": "k"}]})
    native["facts"]["files"] = value["facts"]["files"]
    verdict = golden_replies.compare(golden, native)
    assert "missing sections ['calls']" in verdict.mismatches[0]
    assert "allowance" in verdict.mismatches[0]


def test_an_allowed_subset_compares_everything_else_and_names_the_skipped_section() -> None:
    golden, value = _golden(imports=[{"kind": "k"}], calls=[{"kind": "c"}])
    native = _reply({"imports": [{"kind": "k"}]})
    verdict = golden_replies.compare(golden, native, ALLOW_CALLS)
    assert verdict.mismatches == ()
    assert verdict.compared == ("imports", "rest")
    assert verdict.skipped == ("calls",) and verdict.reason == ALLOW_CALLS.reason
    native["facts"]["files"] = [{"path": "<root>/other.ts"}]
    assert (
        verdict.mismatches == () and golden_replies.compare(golden, native, ALLOW_CALLS).mismatches
    )
    native["facts"]["files"] = value["facts"]["files"]
    native["facts"]["sections"][0]["records"] = []
    assert golden_replies.compare(golden, native, ALLOW_CALLS).mismatches


def test_an_allowance_covers_only_the_sections_that_it_names() -> None:
    golden, _ = _golden(imports=[{"kind": "k"}], calls=[], symbols=[])
    native = _reply({"imports": [{"kind": "k"}]})
    problems = golden_replies.compare(golden, native, ALLOW_CALLS).mismatches
    assert "symbols" in problems[0] and "calls" not in problems[0]
    claims_more = _reply({"imports": [{"kind": "k"}], "calls": [], "bindings": []})
    assert "bindings" in golden_replies.compare(golden, claims_more, ALLOW_CALLS).mismatches[0]


def _table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(golden_replies, "GOLDEN", tmp_path)
    (tmp_path / "lang").mkdir()
    (tmp_path / "lang" / "allowances.json").write_text(
        json.dumps({"4.4": {"sections": ["calls"], "reason": "No calls yet."}})
    )


def test_the_allowance_comes_from_the_table_and_a_variable_alone_grants_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _table(tmp_path, monkeypatch)
    assert golden_replies.allowance_for("lang", {}) is None
    assert golden_replies.allowance_for("lang", {"ARCHKEEL_GOLDEN_PHASE": "4.4"}) == (
        golden_replies.Allowance(("calls",), "No calls yet.")
    )
    with pytest.raises(golden_replies.GoldenError, match="phase 9"):
        golden_replies.allowance_for("lang", {"ARCHKEEL_GOLDEN_PHASE": "9"})


def test_the_deletion_gate_ignores_every_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _table(tmp_path, monkeypatch)
    environ = {"ARCHKEEL_GOLDEN_PHASE": "4.4", "ARCHKEEL_GOLDEN_GATE": "delete"}
    assert golden_replies.allowance_for("lang", environ) is None
    with pytest.raises(golden_replies.GoldenError, match="ARCHKEEL_GOLDEN_GATE"):
        golden_replies.allowance_for("lang", {"ARCHKEEL_GOLDEN_GATE": "yes"})


def test_a_list_difference_names_the_first_differing_element() -> None:
    long = list(range(100))
    found = golden_replies.differences(long, [*long[:50], 999, *long[51:], 5])
    assert "length 100 != 101" in found[0] and "element [50]: '50' != '999'" in found[0]
    assert len(found[0]) < 200
    assert "length 2 != 3" in golden_replies.differences([1, 2], [1, 2, 3])[0]


def test_the_root_is_replaced_in_each_spelling(tmp_path: Path) -> None:
    reply = _reply({"imports": [{"title": f"{tmp_path.as_posix()}/a and {tmp_path}/b"}]})
    value = golden_replies.canonical(reply, tmp_path)
    assert value["facts"]["sections"][0]["records"][0]["title"] == "<root>/a and <root>/b"


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


def _repo(path: Path) -> Path:
    for args in (
        ("init", "-q"),
        ("config", "user.email", "g@example.invalid"),
        ("config", "user.name", "g"),
    ):
        golden_record.git(path, *args)
    (path / "src").mkdir()
    (path / "src" / "a.py").write_text("a\n")
    golden_record.git(path, "add", "-A")
    golden_record.git(path, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "one")
    return path


def test_the_recorder_sees_a_changed_or_new_source_file(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert golden_record.changed_sources(root, ["src"]) == []
    (root / "src" / "a.py").write_text("b\n")
    (root / "src" / "new.py").write_text("c\n")
    (root / "other.txt").write_text("outside\n")
    assert golden_record.changed_sources(root, ["src"]) == ["src/a.py", "src/new.py"]


def test_the_recorder_refuses_a_dirty_source_unless_told(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(golden_replies, "GOLDEN", tmp_path)
    monkeypatch.setattr(golden_record, "changed_sources", lambda root, paths: ["src/a.py"])
    monkeypatch.setattr(golden_record, "cases", lambda language: {"c": golden_record.ROOT / "x"})
    with pytest.raises(golden_replies.GoldenError, match="not committed.*ALLOW_DIRTY"):
        golden_record.record("lang", ["c"], "why")


def test_the_recorder_names_the_missing_variables(capsys: pytest.CaptureFixture[str]) -> None:
    assert golden_record.main(["--reason", "why"]) == 2
    assert "LANGUAGE and CASE are required" in capsys.readouterr().out
    assert golden_record.main(["--language", "nope", "--case", "all", "--reason", "x"]) == 2
    assert "no cases for language 'nope'" in capsys.readouterr().out


def test_git_keeps_the_golden_sources_in_lf_and_the_replies_binary() -> None:
    root = Path(__file__).parents[1]

    def attributes(path: str) -> str:
        return golden_record.git(root, "check-attr", "text", "eol", "binary", "--", path)

    source = attributes("tests/golden/typescript/sources/excalidraw-math/src/index.ts")
    assert "text: set" in source and "eol: lf" in source
    assert "binary: set" in attributes("tests/golden/typescript/h-typescript.json.gz")


def _covered() -> tuple[dict[str, set[str]], set[str], dict[str, int]]:
    kinds: dict[str, set[str]] = {}
    features: set[str] = set()
    counts: dict[str, int] = {}
    for case in golden_record.cases("typescript"):
        digest = golden_replies.load("typescript", case).digest
        for name, section in digest["sections"].items():
            kinds.setdefault(name, set()).update(section["kinds"])
        features.update(digest["features"])
        for key, count in digest["rest"]["counts"].items():
            counts[key] = counts.get(key, 0) + count
    return kinds, features, counts


def test_every_kind_and_feature_that_the_typescript_collector_emits_has_golden_coverage() -> None:
    from archkeel.analyzer.typescript import collect, syntax
    from archkeel.ir.facts import SOURCE_SCRIPT_GLOBAL_KIND, ForbiddenConstructKind

    classes = {
        syntax.DefinitionKind.CLASS,
        syntax.DefinitionKind.INTERFACE,
        syntax.DefinitionKind.ENUM,
    }
    emitted = {
        "imports": {form.value for form in syntax.ReferenceForm} | {SOURCE_SCRIPT_GLOBAL_KIND},
        "unknowns": {kind.value for kind in collect._GapKind},
        "symbols": {"class" if d in classes else d.value for d in syntax.DefinitionKind},
        "calls": {"calls"},
        # The collector writes this kind as a literal; collect.py is at its line ratchet (AD-314).
        "references": {"references", "script_namespace_effect"},
        "bindings": {"bindings"},
        "constructs": {ForbiddenConstructKind.STRING_LITERAL_COMPARE.value},
    }
    assert set(emitted) == {section.value for section in collect._SECTIONS}
    kinds, features, _ = _covered()
    missing = {name: sorted(want - kinds.get(name, set())) for name, want in emitted.items()}
    assert {name: kind for name, kind in missing.items() if kind} == {}
    optional = {"script-globals-v1", collect._BUNDLER_FEATURE}
    assert set(collect._FEATURES) | optional <= features


def test_the_fields_that_the_typescript_collector_never_fills_stay_empty() -> None:
    folder = Path(__file__).parents[1] / "src/archkeel/analyzer/typescript"
    names = ("type_shapes", "uncertain_reexports", "candidate_evidence")
    users = [f.name for f in folder.glob("*.py") if any(name in f.read_text() for name in names)]
    assert users == [], f"{users} now fill a field with no golden coverage: add a case"
    counts = _covered()[2]
    assert [name for name in names if counts[name]] == []


IMPORT_FORM_GAPS = (
    "Unobserved triple-slash reference",
    "Computed dynamic_import cannot be resolved",
    "Computed require cannot be resolved",
    "Package imports are not observed",
    "Package exports patterns are not observed",
    "Package self-reference is not observed",
    "Local alias runtime conditions are not proven",
    "CommonJS runtime file is unavailable",
)


def test_each_import_bearing_form_of_the_typescript_grammar_has_a_golden_case() -> None:
    titles: set[str] = set()
    for case in golden_record.cases("typescript"):
        full = golden_replies.load("typescript", case).full
        sections = {
            s["name"]: s["records"]
            for s in (full or {"facts": {"sections": []}})["facts"]["sections"]
        }
        titles.update(str(record.get("title", "")) for record in sections.get("unknowns", []))
    missing = [gap for gap in IMPORT_FORM_GAPS if not any(gap in title for title in titles)]
    assert missing == [], f"no golden case holds a gap for: {missing}"
