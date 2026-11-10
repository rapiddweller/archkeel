# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Write `architecture.json` through the Rust store when a collection uses it (AD-346, opt-in).

The Python check holds only the read-set of the stored records, so the Python writer must not
write that observation: `canonical_report_bytes` refuses it. `report_bytes` passes the parts of
the shell to the store and names each stored record and evidence entry by its id.
"""

from __future__ import annotations

from dataclasses import replace

from archkeel.ir.codec_observation import canonical_report_bytes as _canonical_report_bytes
from archkeel.ir.codec_observation import observation_payload
from archkeel.ir.facts import Evidence, Record, RecordData
from archkeel.ir.model import CLASSIFIED_SECTIONS, Observation, RawJson
from archkeel.ir.store_seam import StoreSeam, active_store


def canonical_report_bytes(model: Observation | dict[str, RawJson]) -> bytes:
    """The Python writer; it refuses an observation while a store holds the collection."""
    if isinstance(model, Observation) and active_store() is not None:
        raise ValueError("the Rust store writes this observation (AD-346): use report_bytes")
    return _canonical_report_bytes(model)


def _placeholder(record: Record, store: StoreSeam) -> Record:
    """A stored record as its id alone; the store writes the saved record (AD-346)."""
    if not store.holds_record(record.id):
        return record
    return Record(record.id, record.evidence_class, "", "", "", (), (), (), (), (), RecordData())


def _entries(records: RawJson, store: StoreSeam) -> RawJson:
    if not isinstance(records, list):
        return records
    return [
        item["id"]
        if isinstance(item, dict) and isinstance(item["id"], str) and store.holds_record(item["id"])
        else item
        for item in records
    ]


def store_payload(observation: Observation, store: StoreSeam) -> dict[str, RawJson]:
    """The observation payload with the id of each stored record and evidence entry.

    A stored entry enters `observation_payload` as an empty placeholder, so the payload of the
    shell does not copy the read-set of the stored records.
    """
    light = replace(
        observation,
        sections=tuple(
            replace(section, records=tuple(_placeholder(item, store) for item in section.records))
            for section in observation.sections
        ),
        coverage=replace(
            observation.coverage,
            failures=tuple(_placeholder(item, store) for item in observation.coverage.failures),
        ),
        evidence=tuple(
            Evidence(item.id, "", 0, 0, 0, "") if store.holds_evidence(item.id) else item
            for item in observation.evidence
        ),
    )
    payload = observation_payload(light)
    for name in CLASSIFIED_SECTIONS:
        payload[name] = _entries(payload[name], store)
    coverage = payload["coverage"]
    if isinstance(coverage, dict):
        coverage["failures"] = _entries(coverage["failures"], store)
    evidence = payload["evidence"]
    if isinstance(evidence, list):
        payload["evidence"] = [
            item["id"]
            if isinstance(item, dict)
            and isinstance(item["id"], str)
            and store.holds_evidence(item["id"])
            else item
            for item in evidence
        ]
    return payload


def report_bytes(observation: Observation) -> bytes:
    """The canonical `architecture.json` of one fresh observation."""
    store = active_store()
    if store is None:
        return _canonical_report_bytes(observation)
    return store.write(store_payload(observation, store))
