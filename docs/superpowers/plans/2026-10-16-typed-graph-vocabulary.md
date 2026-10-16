# Typed Graph Vocabulary Implementation Plan

> **For agentic workers:** Use the already-read Superpowers executing-plans, TDD and verification workflow.

**Goal:** Graph, UML assessment and graph wire control use domain-owned nominal values while retaining every supported wire spelling and UNKNOWN rule.
**Architecture:** architecture_graph owns graph kinds, visibility, provenance, resolution, completeness, graph versions and assessments. Identical model.RuleVerdict remains its AssessmentStatus facade; observer completion, comparability and declaration status stay distinct. Graph codecs convert once; source/Target builders and UML comparisons consume the owned values.
**Tech Stack:** Python 3.11 StrEnum, frozen dataclasses, pytest, native source observation, Ruff, mypy.
**Spec:** Expanded #542 explicitly includes parser/protocol strings. Preserve existing graph classes, schemas, extension language strings and valid legacy wire inputs.

## Global Constraints

- Preserve historical graph, comparison and report schema bytes and wire values.
- Maintain UNKNOWN/absence/inventory semantics and invalid-reference validation.
- No global miscellaneous enum, generic conversion framework, enum.value comparisons or JSON-key enum collection.
- DecisionMaker architect/agent is a closed contract role; amendment.decided_by remains a free-form actor.
- Language comparison consumes the collector-owned facts.Language enum; graph language data stays open to extensions.
- Add no measured debt relative to the exact integrated predecessor. Preserve its tightened UNKNOWN and unresolved-call caps without any allowance increase; violations=0.
- Remote isolated branches and hosted checks replace unavailable local executor operations.

## Review Focus

- Every supported graph/report version and old default remains accepted with unchanged bytes.
- Closed rule/role metadata shares identity without a graph/model import cycle.
- Legacy valid direct construction and codec output both feed correct enum decisions.
- Missing/partial inventory still yields UNKNOWN, never invented PASS or FAIL.
- Schema generation preserves enum ordering, subset domains and exact historical schemas.

### Task 1: Nominal graph vocabulary and consumers

**Files:** ir/architecture_graph.py, ir/graph_codec.py, ir/source_graph.py, ir/target_graph.py, check/uml_compare.py, check/uml_evaluation.py; necessary shared-status producers/consumers, schema tool, owned Target/guards, tests and docs.
**Interfaces:** Existing graph dataclasses and graph_bytes/parse_graph/comparison/report APIs remain. AssessmentStatus is one shared type. Closed graph domains retain existing public names, now nominal enums. Model aliases/reexports stay compatible.

- [x] Add real native/wire/schema identity and fixed authored Target/guard mutation controls.
- [x] Run hosted RED on the clean State predecessor.
- [x] Replace graph vocabulary aliases, convert wire tags once and update actual builders/decisions.
- [x] Reuse collector Language predecessor when available, preserving its exact implementation and ancestry.
- [x] Protect genuinely migrated whole modules, with no parser exemption; document remaining source-profile control stages.
- [ ] Verify graph/UML/source/Target/codec/report regressions, exact schema drift, Ruff/mypy/hygiene and own baseline.
- [ ] Supply the clean implementation and normal v2 amendment to parent for full combined tests, independent Astra and PR integration.
