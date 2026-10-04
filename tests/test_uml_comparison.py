# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""UML conformance uses recorded facts and coverage, never the absence of findings."""

from dataclasses import replace

import pytest

from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import (
    ArchitectureGraph,
    Coverage,
    Entity,
    Parameter,
    Relationship,
    Signature,
    TargetScope,
    Visibility,
)
from archkeel.ir.facts import Evidence

PROOF = Evidence("proof", "sample.py", 1, 1, 0, "def run(value): ...")


def _entity(identifier, kind, name, parent=None, **changes):
    return Entity(
        identifier,
        kind,
        name,
        "python",
        parent_id=parent,
        presence="defined",
        evidence_ids=("proof",),
        record_ids=(identifier,),
        **changes,
    )


def _intent(entity, **changes):
    return replace(
        entity,
        presence="planned",
        evidence_ids=(),
        record_ids=(),
        responsibilities=("Own the operation.",),
        provenance=("docs/target.md",),
        **changes,
    )


def _graphs(*, complete=True):
    module = _entity("module", "module", "sample")
    operation = _entity(
        "run",
        "function",
        "sample.run",
        "module",
        visibility=Visibility("public", "convention"),
        signature=Signature((Parameter("value", "int", "positional", None, True),), "str"),
    )
    observed = ArchitectureGraph(
        "observed",
        (module, operation),
        coverage=(
            Coverage(
                "module",
                ("function",),
                ("calls",),
                "complete" if complete else "partial",
                None if complete else "limited",
            ),
        ),
        evidence=(PROOF,),
    )
    target = ArchitectureGraph("declared", (_intent(module), _intent(operation)))
    return observed, target


def _assessments(observed, target, aspect):
    return [item for item in compare_graphs(observed, target).assessments if item.aspect == aspect]


def test_known_operations_match_and_preserve_definition_and_source_evidence():
    observed, target = _graphs()
    findings = compare_graphs(observed, target).assessments
    assert findings
    assert {item.status for item in findings} == {"PASS"}
    signature = next(item for item in findings if item.aspect == "signature")
    assert signature.observed_ids == ("run",)
    assert signature.evidence_ids == ("proof",)
    assert signature.fact_ids == ("run",)


@pytest.mark.parametrize("complete,expected", [(True, "FAIL"), (False, "UNKNOWN")])
def test_missing_operation_requires_complete_inventory(complete, expected):
    observed, target = _graphs(complete=complete)
    observed = replace(observed, entities=observed.entities[:1])
    missing = next(
        item for item in _assessments(observed, target, "existence") if item.subject_id == "run"
    )
    assert missing.status == expected
    assert missing.change == ("missing" if complete else "unavailable")
    if complete:
        assert missing.fact_ids == ("module",)


def test_same_name_definitions_are_ambiguous_and_not_arbitrarily_matched():
    observed, target = _graphs()
    observed = replace(
        observed,
        entities=(
            *observed.entities,
            replace(observed.entities[1], id="again", record_ids=("again",)),
        ),
    )
    match = next(
        item for item in _assessments(observed, target, "existence") if item.subject_id == "run"
    )
    assert match.status == "UNKNOWN" and match.change == "ambiguous"
    assert set(match.observed_ids) == {"run", "again"}


@pytest.mark.parametrize("aspect", ["visibility", "signature"])
def test_known_signature_or_visibility_conflict_is_failure(aspect):
    observed, target = _graphs()
    operation = target.entities[1]
    operation = (
        replace(operation, visibility=Visibility("private", "declared"))
        if aspect == "visibility"
        else replace(operation, signature=replace(operation.signature, returns="int"))
    )
    target = replace(target, entities=(target.entities[0], operation))
    assert _assessments(observed, target, aspect)[0].status == "FAIL"


def test_unknown_legacy_parameter_metadata_cannot_prove_signature_conformance():
    observed, target = _graphs()
    operation = replace(
        observed.entities[1], signature=Signature((Parameter("value", "int"),), "str")
    )
    observed = replace(observed, entities=(observed.entities[0], operation))
    assert _assessments(observed, target, "signature")[0].status == "UNKNOWN"


def test_kind_conflict_is_not_a_missing_or_matching_operation():
    observed, target = _graphs()
    observed = replace(
        observed,
        entities=(
            observed.entities[0],
            replace(observed.entities[1], kind="class", signature=None),
        ),
    )
    result = _assessments(observed, target, "kind")
    assert result[0].status == "FAIL" and result[0].change == "changed"


def _connections(resolution="resolved", kind="calls"):
    observed, target = _graphs()
    helper = _entity("helper", "function", "sample.helper", "module")
    actual = Relationship(
        "site",
        kind,
        "run",
        "helper" if resolution == "resolved" else None,
        resolution,
        candidate_ids=("helper",) if resolution == "partial" else (),
        expression="helper",
        evidence_ids=("proof",),
        record_ids=("site",),
    )
    expected = Relationship("expected", "calls", "run", "helper", provenance=("docs/target.md",))
    return (
        replace(observed, entities=(*observed.entities, helper), relationships=(actual,)),
        replace(target, entities=(*target.entities, _intent(helper)), relationships=(expected,)),
    )


def test_resolved_directed_calls_keep_all_source_sites():
    observed, target = _connections()
    observed = replace(
        observed,
        relationships=(
            *observed.relationships,
            replace(observed.relationships[0], id="second", record_ids=("second",)),
        ),
    )
    result = _assessments(observed, target, "relationship")[0]
    assert result.status == "PASS"
    assert set(result.observed_ids) == {"site", "second"}


@pytest.mark.parametrize("resolution", ["partial", "unresolved"])
def test_call_candidates_never_satisfy_declared_calls(resolution):
    observed, target = _connections(resolution)
    result = _assessments(observed, target, "relationship")[0]
    assert result.status == "UNKNOWN"
    assert result.observed_ids == ("site",)


@pytest.mark.parametrize("change", ["reverse", "imports"])
def test_imports_or_reverse_calls_do_not_satisfy_the_required_call(change):
    observed, target = _connections(kind="imports" if change == "imports" else "calls")
    if change == "reverse":
        observed = replace(
            observed,
            relationships=(
                replace(observed.relationships[0], source_id="helper", target_id="run"),
            ),
        )
    assert _assessments(observed, target, "relationship")[0].status == "FAIL"


@pytest.mark.parametrize("mode,expected", [("open", "PASS"), ("closed", "FAIL")])
def test_closed_scopes_reject_known_unlisted_entities_but_open_scopes_allow_them(mode, expected):
    observed, target = _graphs()
    extra = _entity("extra", "function", "sample.extra", "module")
    observed = replace(observed, entities=(*observed.entities, extra))
    target = replace(
        target,
        target_scopes=(
            TargetScope("module", mode, "Own this boundary.", ("docs/target.md",), ("function",)),
        ),
    )
    results = _assessments(observed, target, "completeness")
    assert results and {item.status for item in results} == {expected}


def test_closed_scope_without_coverage_is_unknown_even_when_every_listed_entity_matches():
    observed, target = _graphs(complete=False)
    target = replace(
        target,
        target_scopes=(
            TargetScope(
                "module", "closed", "Own this boundary.", ("docs/target.md",), ("function",)
            ),
        ),
    )
    assert _assessments(observed, target, "completeness")[0].status == "UNKNOWN"


def test_entity_with_different_lexical_parent_does_not_satisfy_containment():
    observed, target = _graphs()
    other = _entity("other", "module", "elsewhere")
    observed = replace(
        observed,
        entities=(*observed.entities[:1], replace(observed.entities[1], parent_id="other"), other),
    )
    assert _assessments(observed, target, "containment")[0].status == "FAIL"


def test_observed_graph_cannot_be_used_as_its_own_target():
    observed, _ = _graphs()
    with pytest.raises(ValueError):
        compare_graphs(observed, observed)


def test_dependency_permission_is_not_a_required_call_or_a_second_policy():
    observed, target = _graphs()
    owners = tuple(
        Entity(
            identity,
            "component",
            identity,
            "architecture",
            presence="planned",
            provenance=("docs/target.md",),
        )
        for identity in ("a", "b")
    )
    permission = Relationship(
        "permission",
        "requires",
        "a",
        "b",
        through=("b.api",),
        decided_by="architect",
        reason="Use the API.",
        provenance=("docs/target.md",),
    )
    wanted = replace(target, entities=(*owners, *target.entities), relationships=(permission,))
    assert compare_graphs(observed, wanted) == compare_graphs(observed, target)
    empty = replace(wanted, entities=owners)
    assert compare_graphs(observed, empty).status == "UNKNOWN"


def test_closed_relationship_scope_does_not_reclassify_ambiguous_endpoints_as_unlisted():
    observed, target = _connections()
    observed = replace(
        observed,
        entities=(*observed.entities, replace(observed.entities[1], id="run-again")),
    )
    target = replace(
        target,
        target_scopes=(
            TargetScope(
                "module", "closed", "Own calls.", ("docs/target.md",), relationship_kinds=("calls",)
            ),
        ),
    )
    result = compare_graphs(observed, target)
    assert result.status == "UNKNOWN"
    assert not any(item.status == "FAIL" for item in result.assessments)


def test_core_correspondence_retains_scope_identity_and_ambiguous_definitions():
    observed, target = _connections()
    owner = Entity(
        "owner",
        "component",
        observed.entities[0].qualified_name,
        "architecture",
        presence="planned",
        provenance=("docs/target.md",),
    )
    target = replace(target, entities=(owner, *target.entities))
    first = compare_graphs(observed, target)
    identities = {item.target_id: item.observed_ids for item in first.correspondences}
    assert identities[owner.id] == (observed.entities[0].id,)
    assert identities["run"] == ("run",)
    observed = replace(
        observed, entities=(*observed.entities, replace(observed.entities[1], id="run-again"))
    )
    ambiguous = compare_graphs(observed, target)
    assert next(
        item.observed_ids for item in ambiguous.correspondences if item.target_id == "run"
    ) == ("run", "run-again")
    assert ambiguous.status == "UNKNOWN"


@pytest.mark.parametrize("kind", ["inherits", "realizes", "creates", "instance_of"])
def test_absent_relationships_without_adapter_coverage_are_unknown(kind):
    observed, target = _connections()
    observed = replace(observed, relationships=())
    target = replace(target, relationships=(replace(target.relationships[0], kind=kind),))
    assert _assessments(observed, target, "relationship")[0].status == "UNKNOWN"


def test_unknown_visibility_basis_cannot_prove_language_access_rules():
    observed, target = _graphs()
    observed = replace(
        observed,
        entities=(
            observed.entities[0],
            replace(observed.entities[1], visibility=Visibility("public")),
        ),
    )
    assert _assessments(observed, target, "visibility")[0].status == "UNKNOWN"


def test_empty_target_does_not_claim_conformance():
    observed, _ = _graphs()
    assert compare_graphs(observed, ArchitectureGraph("declared")).status == "UNKNOWN"


def test_two_completeness_kinds_in_one_scope_have_distinct_assessment_ids():
    observed, target = _graphs()
    target = replace(
        target,
        target_scopes=(
            TargetScope("module", "closed", "Own functions.", ("docs/target.md",), ("function",)),
            TargetScope(
                "module", "closed", "Own calls.", ("docs/target.md",), relationship_kinds=("calls",)
            ),
        ),
    )
    result = compare_graphs(observed, target)
    assert len({item.id for item in result.assessments}) == len(result.assessments)
    result.validate()


def test_partial_child_inventory_prevents_a_closed_parent_scope_from_passing():
    observed, target = _graphs()
    package = _entity("package", "package", "root")
    module = replace(observed.entities[0], qualified_name="root.sample")
    operation = replace(observed.entities[1], qualified_name="root.sample.run")
    observed = replace(
        observed,
        entities=(package, module, operation),
        coverage=(
            Coverage("package", ("function",), status="complete"),
            Coverage(
                "module", ("function",), status="partial", reason="conditional definitions omitted"
            ),
        ),
    )
    target = replace(
        target,
        entities=(_intent(package), _intent(module), _intent(operation)),
        target_scopes=(
            TargetScope("package", "closed", "Own functions.", ("docs/target.md",), ("function",)),
        ),
    )
    assert _assessments(observed, target, "completeness")[0].status == "UNKNOWN"


@pytest.mark.parametrize("kind", ["function", "inherits"])
def test_complete_child_inventory_cannot_certify_an_unmeasured_parent(kind):
    observed, target = _graphs()
    entities = (kind,) if kind == "function" else ()
    relationships = (kind,) if kind == "inherits" else ()
    observed = replace(
        observed,
        coverage=(Coverage("run", entities, relationships, "complete"),),
    )
    target = replace(
        target,
        target_scopes=(
            TargetScope(
                "module",
                "closed",
                "Own this boundary.",
                ("docs/target.md",),
                entities,
                relationships,
            ),
        ),
    )
    assert _assessments(observed, target, "completeness")[0].status == "UNKNOWN"


def test_complete_sibling_inventory_cannot_prove_a_missing_operation():
    observed, target = _graphs()
    observed = replace(
        observed,
        coverage=(Coverage("run", ("function",), status="complete"),),
    )
    missing = replace(target.entities[1], id="missing", qualified_name="sample.missing")
    target = replace(target, entities=(*target.entities, missing))
    result = next(
        item for item in _assessments(observed, target, "existence") if item.subject_id == "missing"
    )
    assert result.status == "UNKNOWN"


def test_ambiguous_self_relationship_preserves_each_definition_identity_once():
    observed, target = _graphs()
    observed = replace(
        observed, entities=(*observed.entities, replace(observed.entities[1], id="again"))
    )
    target = replace(
        target,
        relationships=(
            Relationship("self-call", "calls", "run", "run", provenance=("docs/target.md",)),
        ),
    )
    result = _assessments(observed, target, "relationship")[0]
    assert result.status == "UNKNOWN"
    assert result.observed_ids == ("again", "run")


def test_referenced_endpoint_metadata_cannot_be_silently_treated_as_conforming():
    observed, target = _graphs()
    observed = replace(
        observed,
        entities=(
            observed.entities[0],
            replace(
                observed.entities[1],
                kind="symbol",
                presence="referenced",
                parent_id=None,
                signature=None,
                visibility=Visibility(),
            ),
        ),
    )
    target = replace(
        target, entities=(target.entities[0], replace(target.entities[1], presence="referenced"))
    )
    result = compare_graphs(observed, target)
    assert result.status == "UNKNOWN"
    assert {item.status for item in result.assessments if item.subject_id == "run"} == {"UNKNOWN"}


def test_a_referenced_namespace_cannot_prove_the_open_component_scope_exists():
    observed, _ = _graphs()
    observed = replace(observed, entities=(replace(observed.entities[0], presence="referenced"),))
    owner = Entity(
        "owner",
        "component",
        "sample",
        "architecture",
        presence="planned",
        provenance=("docs/target.md",),
    )
    target = ArchitectureGraph(
        "declared",
        (owner,),
        target_scopes=(
            TargetScope("owner", "open", "Own functions.", ("docs/target.md",), ("function",)),
        ),
    )
    assert compare_graphs(observed, target).status == "UNKNOWN"
