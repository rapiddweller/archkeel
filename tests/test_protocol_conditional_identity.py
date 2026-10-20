# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from test_exact_module_ownership import _component, _observe_tree

from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule


def _contract(protocol: str = "sample.core.Reader") -> dict[str, object]:
    return {
        "schema_version": "3.9.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            {
                "id": "READER",
                "kind": "protocol_declarations",
                "source": "sample.core",
                "protocol": protocol,
                "selectors": [{"role": "parameter", "name": "client", "visibility": "all"}],
                "rationale": "Selected API parameters use the canonical Reader.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }


def _assessment(tmp_path, files: dict[str, str], protocol: str = "sample.core.Reader"):
    result = _observe_tree(tmp_path, files, _contract(protocol))
    assert result.observation is not None, result.coverage
    [assessment] = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    return assessment


def test_unconditional_protocol_identity_remains_proven(tmp_path):
    assessment = _assessment(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "from typing import Protocol\n"
                "class Reader(Protocol): ...\n"
                "def consume(client: Reader): pass\n"
            ),
        },
    )

    assert assessment.status.value == "PASS"
    assert assessment.evaluation_proven


def test_conditionally_defined_protocol_identity_is_unknown(tmp_path):
    assessment = _assessment(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "from typing import TYPE_CHECKING, Protocol\n"
                "if TYPE_CHECKING:\n"
                "    class Reader(Protocol): ...\n"
                "def consume(client: Reader): pass\n"
            ),
        },
    )

    assert assessment.status.value == "UNKNOWN"
    assert not assessment.evaluation_proven


def test_module_branch_protocol_identity_is_unknown(tmp_path):
    assessment = _assessment(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "from typing import Protocol\n"
                "if PUBLICATION_ENABLED:\n"
                "    class Reader(Protocol): ...\n"
                "def consume(client: Reader): pass\n"
            ),
        },
    )

    assert assessment.status.value == "UNKNOWN"


def test_conditionally_imported_protocol_alias_is_unknown(tmp_path):
    assessment = _assessment(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/ports.py": ("from typing import Protocol\nclass Reader(Protocol): ...\n"),
            "sample/core.py": (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from sample.ports import Reader as Port\n"
                "def consume(client: Port): pass\n"
            ),
        },
        protocol="sample.ports.Reader",
    )

    assert assessment.status.value == "UNKNOWN"


def test_conditionally_imported_qualified_module_protocol_is_unknown(tmp_path):
    assessment = _assessment(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/ports.py": ("from typing import Protocol\nclass Reader(Protocol): ...\n"),
            "sample/core.py": (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    import sample.ports as ports\n"
                "def consume(client: ports.Reader): pass\n"
            ),
        },
        protocol="sample.ports.Reader",
    )

    assert assessment.status.value == "UNKNOWN"


def test_static_imported_protocol_alias_remains_proven(tmp_path):
    assessment = _assessment(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/ports.py": ("from typing import Protocol\nclass Reader(Protocol): ...\n"),
            "sample/core.py": (
                "from sample.ports import Reader as Port\ndef consume(client: Port): pass\n"
            ),
        },
        protocol="sample.ports.Reader",
    )

    assert assessment.status.value == "PASS"
    assert assessment.evaluation_proven


def test_wrong_concrete_identity_remains_a_known_violation(tmp_path):
    assessment = _assessment(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "from typing import Protocol\n"
                "class Reader(Protocol): ...\n"
                "class Concrete: pass\n"
                "def consume(client: Concrete): pass\n"
            ),
        },
    )

    assert assessment.status.value == "FAIL"
    assert assessment.evaluation_proven
