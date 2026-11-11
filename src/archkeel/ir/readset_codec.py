# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the read-set document that the Rust store writes for one reply (AD-346, opt-in).

The store validated the reply, so this decoder checks only the shape that it reads and marks the
facts as validated (`validated_facts.accept_store_facts`). A record of a measured section holds
only the data fields that a rule or a view reads (WP1 of #880). A field of the Python `Record`
that the read-set does not carry is empty: `title`, `fact_ids`, `rule_ids` and `provenance`. The
gaps keep their wire form.
The saved `architecture.json` takes each record from the store, never from this copy.
"""

from __future__ import annotations

import json

from .facts import (
    AnalyzerInfo,
    CollectionCoverage,
    EvidenceClass,
    FactSection,
    RawJson,
    Record,
    SourceFacts,
)
from .facts_codec import (
    ProtocolError,
    _boolean,
    _capabilities,
    _file,
    _freeze_object,
    _input,
    _object,
    _parsed_evidence,
    _profile,
    _runtime_info,
    _section_name,
    _source,
    _target,
    _version,
)
from .facts_codec import _array as _list
from .facts_codec import _record_strings as _strings
from .protocol import CollectionResponse
from .state_codec import parse_state_data
from .validated_facts import accept_store_facts


def _text(item: dict[str, RawJson], key: str) -> str:
    value = item.get(key, "")
    if not isinstance(value, str):
        raise ProtocolError(f"record.{key} must be a string")
    return value


def _record(raw: RawJson) -> Record:
    if not isinstance(raw, dict):
        raise ProtocolError("record must be an object")
    return Record(
        id=_text(raw, "id"),
        # A measured section holds FACT records (the store checks it); a gap keeps its wire form.
        evidence_class=EvidenceClass(_text(raw, "evidence_class") or EvidenceClass.FACT.value),
        area=_text(raw, "area"),
        kind=_text(raw, "kind"),
        title=_text(raw, "title"),
        subjects=_strings(raw.get("subjects"), "record.subjects"),
        evidence_ids=_strings(raw.get("evidence_ids"), "record.evidence_ids"),
        rule_ids=(),
        fact_ids=_strings(raw.get("fact_ids", []), "record.fact_ids"),
        provenance=(),
        data=_freeze_object(raw.get("data")),
    )


def _coverage(value: RawJson) -> CollectionCoverage:
    item = _object(
        value, {"selected_files", "files_read", "files_parsed", "full_scope", "gaps"}, "coverage"
    )
    counts = (item["files_read"], item["files_parsed"])
    if not all(isinstance(count, int) and not isinstance(count, bool) for count in counts):
        raise ProtocolError("coverage counts must be integers")
    return CollectionCoverage(
        _strings(item["selected_files"], "coverage.selected_files"),
        int(str(counts[0])),
        int(str(counts[1])),
        _boolean(item["full_scope"], "coverage.full_scope"),
        tuple(_record(gap) for gap in _list(item["gaps"], "coverage.gaps")),
    )


def decode_read_set(payload: bytes | bytearray) -> CollectionResponse:
    """The facts of a read-set document, marked as validated by the store.

    The store writes the document from closed serde types: it has no duplicate key and no
    non-finite number, so the plain JSON reader reads it once.
    """
    try:
        raw: RawJson = json.loads(payload)
    except (ValueError, RecursionError) as error:
        raise ProtocolError(f"invalid read-set JSON: {error}") from error
    document = _object(raw, {"protocol_version", "provider_sources", "facts"}, "read-set")
    version = _version(document["protocol_version"])
    item = _object(
        document["facts"],
        {
            "profile",
            "adapter",
            "runtime",
            "source",
            "capabilities",
            "inputs",
            "files",
            "imports",
            "sections",
            "coverage",
            "evidence",
            "uncertain_reexports",
            "type_shapes",
            "state",
            "candidate_evidence",
            "provider_bindings",
        },
        "facts",
    )
    adapter = _object(item["adapter"], {"name", "version", "code_digest"}, "adapter")
    sections = []
    for raw in _list(item["sections"], "sections"):
        section = _object(raw, {"name", "records"}, "section")
        records = tuple(_record(record) for record in _list(section["records"], "records"))
        sections.append(FactSection(_section_name(section["name"]), records))
    facts = SourceFacts(
        _profile(item["profile"]),
        AnalyzerInfo(
            _text(adapter, "name"), _text(adapter, "version"), _text(adapter, "code_digest")
        ),
        _runtime_info(item["runtime"], version),
        _source(item["source"]),
        _capabilities(item["capabilities"]),
        tuple(_input(entry) for entry in _list(item["inputs"], "inputs")),
        tuple(_file(entry) for entry in _list(item["files"], "files")),
        tuple(_target(entry) for entry in _list(item["imports"], "imports")),
        tuple(sections),
        _coverage(item["coverage"]),
        tuple(_parsed_evidence(entry) for entry in _list(item["evidence"], "evidence")),
        state=parse_state_data(_freeze_object(item["state"])),
    )
    accept_store_facts(facts)
    return CollectionResponse(facts, version, ())
