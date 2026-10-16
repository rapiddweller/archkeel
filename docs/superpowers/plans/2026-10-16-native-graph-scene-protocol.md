# Native graph scene protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make the complete existing native graph scene projection consume precise nominal protocol values without changing graph identity or visible reports.

**Architecture:** Canonical Python Enums generate wire-identical TypeScript string enums and Map validation ports. A concrete protocol validates unknown input once and returns the original objects. The actual graph projection moves to a strictly checkJs-checked classic-JavaScript owner; Atlas/UI remain unchanged follow-ups.

**Tech Stack:** Python3.11+, TypeScript5.9.3, classic JavaScript, existing pytest/Playwright and GitHub Actions.

**Spec:** docs/superpowers/specs/2026-10-16-native-graph-scene-protocol.md

## Global Constraints

- No any, type-ignore, broad casts, duplicate spelling catalogs, schema-generation framework, bundler or cache framework.
- Canonical vocabularies remain in archkeel.ir.architecture_graph; arbitrary IDs/names/paths remain text.
- Preserve original graph/entity/site identity, full JSON, offline assets and Atlas clone behavior.
- Native JS/TS construct evidence is a separate PARTIAL capability; no whole-browser absence claim.
- No budget/allowance increases or historical JSON snapshots.

## Review Focus

- Same-spelling PASS in different status domains must be rejected statically.
- Unknown and malformed closed values must fail at ingress, including nested member/signature fields.
- Legacy supported graph schemas and valid optional metadata must keep working.
- Repeated projections and separately supplied graphs must retain stable identity without repeated full decoding.
- Full JSON, Mermaid, DOM/CSS, route/filter behavior and packaged asset load order must retain wire text.

## Task 1: Prove the missing real ingress behavior

Files: tests/test_graph_scene_protocol.py; this plan/spec. Auxiliary workflow stays off the product carrier.

- [ ] Write real scene.create runtime tests for invalid origin, entity kind, relationship kind/resolution, presence and comparison status.
- [ ] Run unchanged production source under Chromium. Expected: assertions fail because scene.create currently accepts those invalid values.
- [ ] Record the exact RED run/job and commit tests before product implementation.

Interfaces: consumes the actual current ArchkeelReportScene.create(data); expects unknown input to reject unsupported closed values.

## Task 2: Implement one complete native graph scene boundary

Files: tools/browser_graph_protocol.py; src/archkeel/render/assets/report-graph-vocabulary.ts (generated); report-graph-protocol.ts (concrete DTOs/codecs); report-graph-protocol.js (compiled artifact); report-graph-scene.js (existing projection moved and annotated); report-scene.js (delegate); html.py (asset ordering).

- [ ] Generate only graph Enum domains consumed by this boundary from their canonical classes.
- [ ] Define concrete Graph, Entity, Relationship, Signature, Assessment, SceneContext, SceneNode, SceneEdge and Scene DTOs and predicate-based unknown decoders that return the same objects.
- [ ] Extract existing graph/index/member/containment/projection operations to the actual new classic-JS owner. Replace domain control literals with canonical enum members; keep user string data.
- [ ] Run TypeScript5.9.3 strict checkJs on actual consumer source and protocol. Expected: no compiler errors.
- [ ] Run Task1 tests and existing renderer units. Expected: all valid behavior passes; invalid closed values reject; actual graph objects/full JSON remain unchanged.

Interfaces: protocol decodeReport(unknown), decodeGraph(unknown), decodeViewMode(unknown); projection create(unknown) and the existing native scene methods with concrete inputs/outputs.

## Task 3: Verify source guards, integration and shipping

Files: tests/test_graph_scene_protocol.py; tests/test_report_renderer_units.py (new asset dependency loader); Makefile (deterministic generation/typecheck entry); package acceptance only as necessary; this plan ledger.

- [ ] Mutate actual checked consumer field/return source to raw string, same-spelling wrong domain and widened return. Expected: real compiler errors under the fixed authored API expectations.
- [ ] Verify all generated values encode exactly, reject invalid/foreign inputs and survive structuredClone; zero-token test remains a regression control against accidental numeric migration.
- [ ] Regenerate and compare the actual TS/JS artifacts. Expected: byte-identical output; stale-source mutation fails.
- [ ] Run existing Scene/Mermaid, own graph, navigation, filter Chromium tests; assert original object identity and full JSON before/after repeated projection.
- [ ] Build wheel/sdist and verify the actual protocol/projection assets ship and load offline.
- [ ] Record source cost and same-data initialization/projection timing; run Ruff/mypy/hygiene and the appropriate existing regression gate. Root owns fresh composite native gate, exact amendment and independent final Astra review.

## Pre-flight / ledger

- Task2 produces the precise ports consumed by Task3; Task3 mutations target actual source, not a handwritten substitute.
- The existing Flow/API consumes the same primitive string spellings, so no graph copy or output adapter is needed.
- Pending evidence is explicitly unchecked; no completion claim until actual hosted checks are read.

## Size-budget refinement (accepted by Root)

The measured frozen first candidate was 2,029,535 bytes, above both unchanged 2MB/400KB report budgets. Remove the24 unused generated per-enum decode/encode wrappers; canonical nominal Enums and concrete membership predicates remain. Test invalid numeric status at the real comparison ingress and primitive wire text at actual JSON serialization. Independently measure an auxiliary AST-only publication print with optimization and mangling disabled; do not introduce a production build artifact or packaging change before separate review. Layout deduplication is an independent Root change and is not included here.
