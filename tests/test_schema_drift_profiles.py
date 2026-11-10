# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each profile has the decoded observation shape that it publishes (split from schema drift)."""

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_delta import _model
from test_schema_drift import ROOT, _schema, typescript_export_binding  # noqa: F401

from archkeel.ir.codec import parse_observation
from archkeel.ir.profiles import PROFILES

# A profile that publishes no calls (Rust, AD-351) has no call counts either.
_NO_CALLS = dict.fromkeys(
    (
        "calls_analyzed",
        "calls_resolved",
        "calls_partially_resolved",
        "calls_unresolved",
        "call_resolution_percent",
    )
)


@pytest.mark.parametrize("version", ["2.0.0", "2.1.0", "2.3.0"])
@pytest.mark.parametrize("profile", PROFILES.values(), ids=lambda profile: profile.analyzer)
def test_direct_export_binding_schema_is_typescript_21_only(
    typescript_export_binding,  # noqa: F811
    profile,
    version,
):
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema))
        for schema in (_schema(path.name) for path in (ROOT / "schema").glob("*.json"))
    )
    validator = Draft202012Validator(
        {"$ref": f"urn:archkeel:architecture-ir:decoded:{version}"}, registry=registry
    )
    observation = _model(git_head="a" * 40)
    observation["schema_version"] = version
    observation["analyzer"]["name"] = profile.analyzer
    for section in profile.absent_sections:
        observation[section] = None
    if "calls" in profile.absent_sections:
        observation["coverage"] = {**observation["coverage"], **_NO_CALLS}
    assert validator.is_valid(observation)
    observation["bindings"] = [typescript_export_binding]
    accepted = version in {"2.1.0", "2.3.0"} and profile.analyzer == "archkeel-typescript-imports"
    assert validator.is_valid(observation) is accepted
    if accepted:
        assert parse_observation(observation).records("bindings")[0].data.get("name") == "port"
