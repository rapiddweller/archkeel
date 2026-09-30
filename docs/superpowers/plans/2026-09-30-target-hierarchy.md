# Target Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the declared target hierarchy readable and fully explorable without changing architecture facts.

**Architecture:** Extend the existing render projection with physical frames and dependency ranks. Keep semantic identities and all three existing view states intact; reuse current cards, UML and navigation.

**Tech Stack:** Python 3.11, stdlib graphlib, existing JavaScript/CSS, pytest and Chromium/Playwright 1.62.0.

**Spec:** `docs/superpowers/specs/2026-09-30-target-hierarchy.md`

## Global Constraints

- Preserve canonical semantic tree, ownership, verdicts, IDs, graph keys and Actual/Target/Diff identity; `packages` remains dotted-prefix ownership. No #211/`exact_modules`, new dependency or view tab.
- Use declarations only for Target. Retain every declaration/module and explicit missing/UNKNOWN evidence.
- Default zoom 100%; names ≥14 CSS px, responsibility previews ≥12 CSS px. Test 1440×1000 and 1856×1336 CSS pixels.
- Final screenshots follow Alex's report approval and implementation merge, and must precede release 0.8.2. Inspect all README images; refresh current report/terminal captures and verify captions/counts. Text docs, AD <70 lines, index, roadmap, release notes and demos precede merge.

## Review Focus

1. Runtime → Domains → IO spans physical Engine: framing must not manufacture a cycle (Task 1).
2. A cycle's dependent is residual but not necessarily cyclic; retain all nodes/edges (Task 1).
3. Multiple or unsupported scopes must not duplicate cards or acquire guessed placement (Task 1).
4. Details toggle/resize after deep physical navigation must preserve selection, zoom and return path (Task 2).
5. A missing target or unmatched Diff route must remain explicit and return to its original identity (Tasks 2–3).

## Task 1: Declaration projection and deterministic ranks

**Files:** Modify `src/archkeel/render/html.py`; test `tests/test_target_diagram_acceptance.py`.

**Interfaces:** Preserve `_target_diagrams(target_roots: list[dict[str, object]]) -> dict[str, object]`, `_target_component_node(...)` and existing graph keys. Produce graph `containers`, component `placement` and node `dependency_rank` exactly as the Spec defines; existing explorers stay semantically unchanged.

- [ ] Write `test_target_physical_frames_preserve_semantic_owners` using a hand-built declaration fixture with root, engine, runtime, domains and IO; assert literal component IDs occur once and Runtime → Domains → IO ranks increase, with runtime/IO sharing the engine frame.

```python
assert containers["layout:LAYOUT-ENGINE"]["members"] == ["COMP-IO", "COMP-RUNTIME"]
assert ranks["COMP-RUNTIME"] < ranks["COMP-DOMAINS"] < ranks["COMP-IO"]
assert component_ids == {"COMP-RUNTIME", "COMP-DOMAINS", "COMP-IO"}
```

- [ ] Add literal expected placement cases for explicit namespace, unique package prefix, same-frame multiple scopes, distinct-frame multiple scopes, ambiguous layout and unsupported selector. Verify every target remains reachable, including folded layouts, physical-only/module targets and unmapped entries.
- [ ] Add disconnected, self-loop and two-node-cycle-plus-dependent cases; assert the dependent's rank is null without claiming it is cyclic. Reorder declarations/requirements and assert identical presentation output. Test `public`/`through` absent, null, empty and declared with exact rationale/provenance, without observed modules.
- [ ] Run RED: `uv run --locked python -m pytest -q tests/test_target_diagram_acceptance.py -k 'physical_frames or placement or dependency_rank or declared_interfaces'`; record missing behavior, not fixture errors.
- [ ] Implement only presentation metadata and declaration details in existing helpers. Use `graphlib.TopologicalSorter` with each required dependency as its consumer's prerequisite; drain acyclic ready nodes, then invert their depths for consumer-first visual ranks. Leave cyclic residuals and their dependents null. Rank semantic edges before containment. Never import analyzer graph helpers or change ownership.
- [ ] Run the focused tests GREEN, then `make check`; report every failure explicitly. Run `make self-observation` only if the saved run is stale, and commit regeneration separately.
- [ ] Review diff, stage only this task and commit `Show declared physical target frames`.

## Task 2: Readable layout and physical navigation

**Files:** Modify `src/archkeel/render/assets/flow.js`, `src/archkeel/render/assets/archkeel-report.css`, `src/archkeel/render/html.py`; test both acceptance files under `tests/`.

**Interfaces:** Consume Task 1's graph metadata. Preserve existing target node/edge IDs and targetPath/view matching; add the four stable browser attributes from the Spec. Use existing `renderTargetDiagram` and state/selection machinery, not a second explorer.

- [ ] Write `test_target_hierarchy_browser_navigation` on real generated HTML at both required viewports. Assert viewport-scale canvas, 100% zoom, literal expected root owners and engine members, non-overlapping cards, readable CSS font sizes and complete current-scope counts.
- [ ] Add keyboard frame/card Open, root → engine → runtime → tasks, back/breadcrumb and direct-root navigation; details must expose complete responsibilities and declared interfaces. Check Actual → Target → Diff → Target restores exact identity and unmatched physical route.
- [ ] Add Details-toggle and resize probes: snapshot selected node, path, zoom and scroll anchor before/after; assert unchanged, `aria-expanded` correct and full-width canvas restored. Missing targets/UNKNOWN may not silently disappear under filters.
- [ ] Run RED with `make report-browser OUTPUT=/private/tmp/archkeel224-task2-red`; retain expected functional failures before source edits.
- [ ] Implement physical lanes/frames and semantic-rank positions in `renderTargetDiagram`; grow explorer width/height with CSS, retain native scrolling and explicit Fit. Reuse card/UML rendering. Implement explicit frame Open and Details toggle without changing semantic ownership or global filters.
- [ ] Run `make report-browser OUTPUT=/private/tmp/archkeel224-task2-green`, then `make check`; regenerate stale D-self separately. Review diff and commit `Make target hierarchy readable and navigable`.

## Task 3: Demos, documentation and integrated acceptance

**Files:** Modify `fixtures/demo_catalog_layout.py`, relevant existing demo tests, `tools/report_browser.py` only if repeatable captures require it, `README.md`, `docs/architecture-demo.md`, `docs/architecture/archkeel.md`, `docs/roadmap.md`, `RELEASE_NOTES.md`. Create the next available `docs/architecture/decisions/ad-<n>-target-physical-frames.md` (<70 lines).

**Interfaces:** Consume the unchanged declaration format and Tasks 1–2's report. No final documentation screenshot assets before human approval/merge.

- [ ] Add runnable positive declared-hierarchy and negative missing/ambiguous/cyclic placement demos with literal expected verdict/evidence. Existing clean/FAIL/UNKNOWN semantics must remain unchanged; presentation order is not an architectural layer.
- [ ] Execute the new demo tests RED where their expected report presentation is absent, then GREEN; retain the already verified source behavior rather than manufacturing failures in prose tests.
- [ ] Write concise decision, index/roadmap rows, release notes and behavior text covering physical versus semantic containment, placement basis, unresolved rank and Details/navigation. Avoid final candidate screenshot references.
- [ ] Run `make gate` and `make report-browser OUTPUT=/private/tmp/archkeel224-final-browser`; report platform-specific failures with exact independent Linux proof rather than hiding them. Use absolute candidate PYTHONPATH or unset it in cwd-changing tests.
- [ ] Build a candidate wheel and generate fresh CE HTML/JSON. Capture root/runtime/tasks at 1440×1000 and 1856×1336 and traverse tasks → generate → workers with real UI. Assert unchanged CE verdict/UNKNOWN/inventory unless authoritative CE source changed.
- [ ] Commit coherent changes, independent Luna QA and Astra whole-branch review, then push a Draft PR linked to #224. Present candidate to Alex; merge/close #224 and final screenshot refresh wait for his visual approval. Audit every README image and prepare refreshed captures now; after merge update all current report/terminal assets and their captions/links in one docs PR. Publish 0.8.2 only after that update and the integrated release gate. Retain still-accurate static artwork/historical images; no unreviewed or stale screenshots in the release.
