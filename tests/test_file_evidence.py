# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-107: a module exists because its file does, so an empty file is still evidence of it.

`root_layout`, `complete_assignment` and a component `namespace` judge a module by its own file.
Their violation cites the module fact, whose evidence quoted line 1; an empty `__init__.py` or
a blank first line left nothing to quote, the trace check refused the violation and the whole
run turned UNKNOWN (issue #153). Each case here pins the same violation for the empty file as
for one with text, and a verdict that stays FAIL.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.check.report import run_report
from archkeel.check.run import inspect_observation
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model
from archkeel.ir.model import SCHEMA_VERSION, Evidence, Observation, Record
from archkeel.ir.trace import trace_valid_violations
from fixtures.architecture_demo import CATALOG

SCHEMA = Path(__file__).parents[1] / "schema"

_PROBE = {"rationale": "Probe.", "provenance": ["docs/architecture/sample.md"]}
_ROOT_LAYOUT = {
    "id": "ROOT",
    "kind": "root_layout",
    "root": "sample",
    "allowed_children": ["sample.keep"],
    "decided_by": "architect",
    **_PROBE,
}
_ASSIGNMENT = {
    "id": "ASSIGN",
    "kind": "complete_assignment",
    "source": "sample",
    "decided_by": "architect",
    **_PROBE,
}
_THE_FILE = (0, 0, 0, "")
# (initializer, the evidence position and excerpt its module fact cites)
_INITIALIZERS = (
    ('"""Extra."""\n', (1, 1, 0, '"""Extra."""')),
    ("", _THE_FILE),
    ("\n", _THE_FILE),
    ("\nVALUE = 1\n", _THE_FILE),
)


def _violation(observation: Observation) -> tuple[Record, Evidence]:
    """The one violation, trace-valid, of a complete observation whose verdict is FAIL."""
    _, verdict = inspect_observation(observation)
    assert verdict == "FAIL"
    (violation,) = trace_valid_violations(observation)
    evidence = {item.id: item for item in observation.evidence}
    (fact,) = (
        item
        for section in observation.sections
        for item in section.records
        if item.id in violation.fact_ids
    )
    (source,) = (evidence[key] for key in fact.evidence_ids)
    return violation, source


def _ir_schema_errors(observation: dict[str, object]) -> list[str]:
    """What the published IR schemas reject in one decoded observation, as test_schema_drift."""
    profile = {"$ref": f"urn:archkeel:architecture-ir:python-decoded:{SCHEMA_VERSION}"}
    schemas = [json.loads(path.read_bytes()) for path in SCHEMA.glob("*.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    validator = Draft202012Validator(profile, registry=registry)
    return [error.message for error in validator.iter_errors(observation)]


def test_the_ir_schemas_accept_a_cited_file_only_in_the_form_the_trace_check_reads(
    tmp_path: Path,
) -> None:
    variant = next(item for item in CATALOG if item.id == "class-a-root-layout-empty-package")
    _, architecture = run_report(
        _prepare_repo(tmp_path, dict(variant.files)), config=CONFIG, analyzer=observe
    )
    assert architecture is not None
    observation = decode_canonical_model(json.loads(architecture))
    evidence = observation["evidence"]
    (cited,) = (item for item in evidence if item["file"] == "shop/extra/__init__.py")

    assert (cited["line"], cited["end_line"], cited["column"], cited["excerpt"]) == (0, 0, 0, "")
    assert _ir_schema_errors(observation) == []
    for field, value in (("excerpt", "import shop"), ("end_line", 1), ("column", 4)):
        malformed = [{**item, field: value} if item is cited else item for item in evidence]
        assert _ir_schema_errors({**observation, "evidence": malformed}), field
