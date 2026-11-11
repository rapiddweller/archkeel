# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-324: the host writes large JSON in pieces and frees each copy as soon as it is made."""

import gc
import json
import re
import tracemalloc
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path

import pytest
from test_explore import _repository

from archkeel.check import report as report_module
from archkeel.check.ports import Language
from archkeel.check.report import run_explore
from archkeel.cli.observe import observer_for
from archkeel.ir import codec_wire
from archkeel.ir.architecture_graph import ArchitectureGraph, ArchitectureReport
from archkeel.ir.codec import (
    canonical_json_bytes,
    canonical_report_bytes,
    decode_canonical_model,
    encode_canonical_model,
    observation_payload,
    write_json,
)
from archkeel.ir.codec_strings import StringTablePolicy, intern_strings
from archkeel.ir.codec_wire import raw_fields
from archkeel.ir.graph_codec import report_bytes, report_payload
from archkeel.ir.model import CLASSIFIED_SECTIONS, Observation
from archkeel.ir.report_graph import architecture_report
from archkeel.render import html as html_renderer

_COMPACT = (",", ":")
_DEFAULT = (", ", ": ")


@pytest.fixture(scope="module")
def observation(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    root = _repository(tmp_path_factory.mktemp("repo"))
    _, _, observed = run_explore(root, observer=observer_for(Language.PYTHON))
    assert observed is not None
    return observed


def _dumps(value: object, separators: tuple[str, str]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=separators).encode()


def test_a_repeated_string_has_one_reference_object() -> None:
    text = "a repeated string that is long enough to be worth a table entry"
    tree, table = intern_strings(
        [[text], [text], [text], [text]], policy=StringTablePolicy.OBSERVATION
    )

    references = [row[0] for row in tree]

    assert table == [text]
    assert references == ["$0"] * 4
    assert len({id(reference) for reference in references}) == 1


def test_raw_fields_equal_the_json_of_asdict_and_share_the_leaves(
    observation: Observation,
) -> None:
    records = [record for section in observation.sections for record in section.records]
    values = [observation, observation.coverage, *observation.evidence, *records]

    for value in values:
        assert _dumps(raw_fields(value), _COMPACT) == _dumps(asdict(value), _COMPACT)
    assert raw_fields(records[0])["id"] is records[0].id


def test_raw_fields_of_a_dataclass_without_fields_is_an_empty_object() -> None:
    @dataclass(frozen=True)
    class Empty:
        pass

    assert raw_fields(Empty()) == {}


_VALUES = [
    {"b": [1, 2.5, None, True], "a": {"z": "é→<", "y": []}, "c": {}},
    [{"k": index, "t": ("x", index)} for index in range(10)],
    {"rows": [{"id": index, "text": f"Zeile {index} →"} for index in range(25)], "n": (1, 2)},
    {"deep": {"deeper": {"deepest": {"bottom": {"x": list(range(9))}}}}},
    {1: "a", 2: ["b"] * 9},
    {"empty": [], "tuple": tuple(range(7)), "single": [0]},
]


@pytest.mark.parametrize("separators", [_COMPACT, _DEFAULT])
@pytest.mark.parametrize("value", _VALUES)
def test_json_in_pieces_equals_json_dumps(
    value: object, separators: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(codec_wire, "_LIST_PIECE", 3)
    out = BytesIO()

    write_json(out, value, separators=separators)

    assert out.getvalue() == _dumps(value, separators)
    assert codec_wire.json_bytes(value, separators=separators, tail=b"\n") == (
        _dumps(value, separators) + b"\n"
    )


def test_json_for_a_script_element_has_no_less_than_sign(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codec_wire, "_LIST_PIECE", 2)
    value = {"</script>": ["<b>", "<i>", "<u>", "ok"]}
    out = BytesIO()

    write_json(out, value, html_safe=True)

    assert out.getvalue() == _dumps(value, _COMPACT).replace(b"<", b"\\u003c")
    assert b"<" not in out.getvalue()


def test_json_in_pieces_peaks_near_the_size_of_its_output() -> None:
    value = {"rows": [{"id": index, "text": f"Zeile {index} → ß"} for index in range(60_000)]}
    size = len(_dumps(value, _COMPACT))
    tracemalloc.start()
    try:
        codec_wire.json_bytes(value, tail=b"\n")
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    # One text for the value holds two bytes for each character; with its copies it takes 5 times.
    assert peak < 2.5 * size


def test_canonical_bytes_equal_the_text_of_json_dumps() -> None:
    model = {"b": [{"é": 1}], "a": ("x", None)}

    assert canonical_json_bytes(model) == (_dumps(model, _COMPACT) + b"\n")


def test_the_encoder_consumes_the_record_sections_of_an_owned_payload(
    observation: Observation,
) -> None:
    expected = canonical_json_bytes(encode_canonical_model(observation_payload(observation)))
    raw = observation_payload(observation)

    encoded = encode_canonical_model(raw, consume=True)

    assert not {*CLASSIFIED_SECTIONS, "evidence"} & raw.keys()
    assert canonical_json_bytes(encoded) == expected
    assert canonical_report_bytes(observation) == expected


def test_the_columnar_report_decodes_back_to_the_payload(observation: Observation) -> None:
    decoded = decode_canonical_model(json.loads(canonical_report_bytes(observation)))

    assert decoded == observation_payload(observation)


def test_a_payload_that_the_caller_owns_is_not_consumed(observation: Observation) -> None:
    raw = observation_payload(observation)
    before = canonical_json_bytes(raw)

    canonical_report_bytes(raw)
    encode_canonical_model(raw)

    assert canonical_json_bytes(raw) == before


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"evidence": {}}, "evidence must be an array"),
        ({"symbols": {}}, "symbols must be an array"),
    ],
)
def test_the_encoder_names_a_section_that_is_no_array(
    observation: Observation, change: dict[str, object], message: str
) -> None:
    raw = observation_payload(observation) | change

    with pytest.raises(ValueError, match=message):
        encode_canonical_model(raw, consume=True)


def _old_report_object(report: ArchitectureReport) -> dict[str, object]:
    """The wire object as the code wrote it before AD-324: asdict of each part, no shared writer."""

    def graph(item: ArchitectureGraph | None) -> dict[str, object] | None:
        if item is None:
            return None
        encoded = asdict(item)
        for intent in encoded["component_intents"]:
            for key in ("layer", "lifecycle"):
                if intent[key] is None:
                    del intent[key]
        return encoded

    return {
        "observed": graph(report.observed),
        "target": graph(report.target),
        "comparison": None if report.comparison is None else asdict(report.comparison),
        "unavailable": report.unavailable,
        "schema_version": report.schema_version,
        "findings": [asdict(item) for item in report.findings],
        "memberships": [asdict(item) for item in report.memberships],
        "decision_gaps": [asdict(item) for item in report.decision_gaps],
    }


def test_report_bytes_equal_json_dumps_of_the_old_wire_object(observation: Observation) -> None:
    report = architecture_report(observation)
    # The fixture must fill every part, so a dropped part changes the bytes.
    assert report.target and report.memberships and report.findings and report.decision_gaps

    old = json.dumps(_old_report_object(report), sort_keys=True, ensure_ascii=False) + "\n"

    assert report_bytes(report) == old.encode("utf-8")
    assert json.loads(json.dumps(report_payload(report))) == json.loads(old)


def test_the_html_payload_is_the_old_wire_object_without_record_ids(
    observation: Observation,
) -> None:
    report = architecture_report(observation)
    wire = _old_report_object(report)
    for graph in (wire["observed"], wire["target"]):
        if isinstance(graph, dict):
            for item in (*graph["entities"], *graph["relationships"]):
                del item["record_ids"]

    _, payload, warning = html_renderer._html_report_payload(report)

    assert warning is None
    assert json.loads(json.dumps(payload)) == json.loads(json.dumps(wire))
    assert "record_ids" not in json.dumps(payload)


def test_text_of_the_input_cannot_fake_the_payload_mark() -> None:
    mark = html_renderer._PAYLOAD_MARK.decode()
    page = html_renderer._document(
        repository=f"repo{mark}", kind="Architecture report", title="t", content=mark
    )

    with pytest.raises(ValueError, match="reserved payload mark"):
        html_renderer._with_payload(page, {})


def test_a_page_holds_its_payload_where_the_mark_is() -> None:
    payload = {"b": ["</script>", "é→"], "a": 1}
    page = b"<script>" + html_renderer._PAYLOAD_MARK + b"</script>"

    assert (
        html_renderer._with_payload(page, payload)
        == b"<script>" + _dumps(payload, _COMPACT).replace(b"<", b"\\u003c") + b"</script>"
    )


@pytest.mark.parametrize("page", [b"<script></script>", b"\x00archkeel-payload\x00" * 2])
def test_a_page_needs_its_mark_exactly_once(page: bytes) -> None:
    with pytest.raises(ValueError, match="reserved payload mark"):
        html_renderer._with_payload(page, {})


def _flow_data(page: bytes) -> dict[str, object]:
    match = re.search(rb'id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    data: dict[str, object] = json.loads(match.group(1))
    return data


def test_the_pages_carry_their_payload_and_no_mark(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    result, encoded, explored = run_explore(root, observer=observer_for(Language.PYTHON))
    assert encoded is not None

    pages = dict(
        html_renderer.render_architecture_pages(
            result,
            encoded,
            repository="repo",
            architecture_href="architecture.json",
            observation=explored,
        )
    )

    assert b"\x00" not in b"".join(pages.values())
    main = _flow_data(pages["architecture.report.html"])
    detail = _flow_data(pages["architecture.detail.html"])
    assert "atlas" in main
    assert detail["initial_view"] == "diagram"
    observed = detail["observed"]
    assert isinstance(observed, dict) and observed["entities"]
    assert all("record_ids" not in item for item in observed["entities"])


def test_explore_frees_the_first_observation_before_the_second_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "repo")

    def alive() -> int:
        gc.collect()
        return sum(isinstance(item, Observation) for item in gc.get_objects())

    before, seen = alive(), []
    real = report_module.observe_repository

    def spy(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        seen.append(alive())
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(report_module, "observe_repository", spy)

    run_explore(root, observer=observer_for(Language.PYTHON))

    assert seen == [before, before]


def test_explore_collects_the_source_once_for_both_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "repo")
    observer = observer_for(Language.PYTHON)
    collector = type(observer.collector)
    real, calls = collector.collect, []

    def spy(self: object, request: object) -> object:
        calls.append(request)
        return real(self, request)  # type: ignore[arg-type]

    monkeypatch.setattr(collector, "collect", spy)

    run_explore(root, observer=observer)

    assert len(calls) == 1
