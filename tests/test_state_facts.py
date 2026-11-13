# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One source collection must reproduce Context evidence under different contracts."""

import pytest

from archkeel.ir.facts_codec import freeze_data
from archkeel.ir.state_codec import parse_state_data, state_data


def test_state_wire_roundtrip_rejects_unknown_event_shapes() -> None:
    from archkeel.ir.state_facts import Assignment, FunctionStateTrace, StateFacts

    facts = StateFacts(
        (),
        (
            FunctionStateTrace(
                "sample.f", "sample", None, None, (), (Assignment(("ctx",), "Bag", None, None),)
            ),
        ),
    )
    assert parse_state_data(state_data(facts)) == facts
    invalid = freeze_data(
        {
            "classes": [],
            "functions": [
                {
                    "scope": "sample.f",
                    "module": "sample",
                    "class_owner": None,
                    "receiver": None,
                    "parameters": [],
                    "events": [{"kind": "unknown"}],
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="event"):
        parse_state_data(invalid)


@pytest.mark.parametrize(
    "event",
    [
        {
            "kind": "assignment",
            "targets": "ctx",
            "constructor": None,
            "annotation": None,
            "alias": None,
        },
        {"kind": "pass", "binding": "ctx", "target": "f", "evidence_id": "e", "rule": "forbidden"},
        {"kind": "attribute", "binding": "ctx", "path": [], "access": "read", "evidence_id": "e"},
        {
            "kind": "attribute",
            "binding": "ctx",
            "path": ["append"],
            "access": "mutation",
            "evidence_id": "e",
        },
        {
            "kind": "attribute",
            "binding": "ctx",
            "path": ["value"],
            "access": "unknown",
            "evidence_id": "e",
        },
        {"kind": "pass", "binding": "ctx", "target": "f", "evidence_id": ""},
    ],
)
def test_state_wire_rejects_malformed_events(event: dict[str, object]) -> None:
    raw = freeze_data(
        {
            "classes": [],
            "functions": [
                {
                    "scope": "sample.f",
                    "module": "sample",
                    "class_owner": None,
                    "receiver": None,
                    "parameters": [],
                    "events": [event],
                }
            ],
        }
    )
    with pytest.raises(ValueError):
        parse_state_data(raw)


@pytest.mark.parametrize("frozen", [0, 1, "true", None])
def test_state_wire_requires_boolean_class_flags(frozen: object) -> None:
    raw = freeze_data(
        {
            "classes": [
                {
                    "qualified_name": "sample.Bag",
                    "module": "sample",
                    "frozen": frozen,
                    "protocol": False,
                    "fields": [],
                    "methods": [],
                    "evidence_ids": [],
                }
            ],
            "functions": [],
        }
    )
    with pytest.raises(ValueError, match="boolean"):
        parse_state_data(raw)
