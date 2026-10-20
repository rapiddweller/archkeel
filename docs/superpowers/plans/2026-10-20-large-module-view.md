# Large module view Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Explorer's "Modules" view stays responsive on large repositories without hiding or altering Core facts.

**Architecture:** Two independent browser-only fixes. (1) Edge pulses animate only for emphasized edges, so an idle page stops repainting. (2) A module-level scene over a fixed budget is not laid out or drawn; the view states the totals and offers the module list, components and Health check instead. Report JSON, payload and rule results stay unchanged.

**Tech Stack:** Vanilla JS assets in `src/archkeel/render/assets/`, ELK 0.12, Playwright browser tests in pytest.

**Spec:** This plan. Evidence below; no separate spec.

## Evidence (2026-10-20, headless Chromium, single runs)

| Case | Modules / edges | Measured |
|---|---|---|
| archkeel self, root "Modules" | 146 / 605 drawn | Idle after ready: main thread busy 5.2 s of 5 s, 12 fps. With `.edge .pulse{animation:none}`: 0.07 s, 60 fps. Scene 11,190 × 10,912 px, fit zoom 7 %. |
| EE, root "Modules" | 1,174 / 5,292 | Ready 7.02 s, of which ELK 6.09 s; ~81,000 DOM nodes; 237 MB JS heap. |
| EE, IO component | 345 / 1,203 | Ready 1.51 s, ELK 1.03 s. |

- Pulse cost: `stroke-dashoffset` animation on every non-declared edge (`archkeel-report.css:1789-1820`, created at `flow.js:485`) is repainted on the main thread every frame.
- Layout cost: `renderAtlas` (`flow.js:2617`) lays out every module of the level via `layoutAtlasScene` on the UI thread.
- Crash itself: not reproduced. Both costs grow with edge count.

## Decisions (confirm before Task 2)

- **D1 Budget:** `MODULE_DIAGRAM_BUDGET = { modules: 80, edges: 300 }`. Basis: 146 modules are already unreadable at fit zoom. CBM's SVG views cap at 40–80 nodes.
- **D2 Pulse rule:** one rule for every view: pulses run only while an element is hovered or selected. Arrows (`marker-end`) still show direction at rest.
- **D3 Over budget:** no partial diagram. A top-N subset needs a ranking that would itself be an unproven claim. The user reaches modules through Components, the list, search or Health check.

## Global Constraints

- Payload, `architecture.json`, rule assessments and Python renderers stay byte-identical. Check with `git diff --stat src/archkeel/render/*.py` = empty.
- Every omission states its counts: total modules, total relationships, budget.
- Regenerate committed runtime bundles with `make browser-runtime-generate`. `make browser-runtime-check` must pass.
- No Web Worker, no canvas or WebGL renderer, no new dependency.
- `prefers-reduced-motion` keeps disabling all pulses (`archkeel-report.css:1892`).

## Review Focus

1. Deep link `?content=modules` or `?module=<id>` into an over-budget level must not start ELK. The notice is shown, and the module detail still opens. Test in Task 2.
2. Target and Diff views over budget use the same gate, since declared modules can exceed it as well. Test in Task 2.
3. Keyboard focus on an edge (`.hit` has `tabindex=0`) counts as emphasis, so its pulse runs. Test in Task 1.
4. Switching from an over-budget level to a component under budget lays out normally, with no stale notice and no stale `layoutState`. Test in Task 2.
5. The Health check matrix is sparse (`flow.js:2586`: one rect per existing cell, labels skipped below 9 px). It is not gated. Task 2 only asserts that it still opens over budget.

---

### Task 1: Pulse only on emphasis

**Files:**
- Modify: `src/archkeel/render/assets/archkeel-report.css:1789-1796` (move `animation` to an emphasis selector)
- Modify: `src/archkeel/render/assets/flow.js` `atlasEmphasize` (~2681) and the UML equivalent that toggles `.dim`. They set `root.dataset.emphasis = focus ? "true" : "false"`.
- Regenerate: `src/archkeel/render/assets/explorer.runtime.js`, `flow.runtime.js`
- Test: `tests/test_atlas_report.py`

**Interfaces:**
- Produces: `root.dataset.emphasis ∈ {"true","false"}`. CSS selector `.flow[data-emphasis="true"] .edge:not(.dim) .pulse` carries `animation: flow-pulse 1.8s linear infinite`. The base `.edge .pulse` has no animation.

- [ ] **Step 1: Write the failing test** `test_module_view_is_idle_until_an_element_is_emphasized(tmp_path)`. Build it from `_nested_repository` like `test_components_and_modules_choice_uses_native_scope_and_survives_return`. Open `?scope=ROOT&content=modules`, wait for `[data-layout-state="ready"]`, then:

```python
pulses = "document.getAnimations().filter(a => a.animationName === 'flow-pulse')"
assert page.evaluate(f"{pulses}.length") == 0
page.locator(".node[data-uml-id]").first.hover()
assert page.evaluate(f"{pulses}.length") > 0
assert page.evaluate(f"{pulses}.every(a => !a.effect.target.closest('.edge').classList.contains('dim'))")
page.mouse.move(1, 1)
assert page.evaluate(f"{pulses}.length") == 0
page.locator(".edge .hit").first.focus()
assert page.evaluate(f"{pulses}.length") > 0
```

- [ ] **Step 2: Run it, expect FAIL** on the first assertion: `uv run --locked python -m pytest -q tests/test_atlas_report.py::test_module_view_is_idle_until_an_element_is_emphasized`
- [ ] **Step 3: Implement** the CSS move and the `data-emphasis` toggle. Edge keyboard focus must call the same emphasis path as hover.
- [ ] **Step 4: Regenerate and pass:** `make browser-runtime-generate`, then the test from Step 2, then `make browser-runtime-check`.
- [ ] **Step 5: Measure, not gate:** re-run the idle probe on the self report (`make report-pages`). Expect busy time < 0.5 s per 5 s and fps ≥ 50. Note the numbers in the commit body.
- [ ] **Step 6: Commit** `fix(report): animate edge pulses only for emphasized elements`

### Task 2: Module diagram budget

**Files:**
- Modify: `src/archkeel/render/assets/report-scene.js` `atlasModuleScene` (:76). It adds `overBudget` and keeps `nodes`/`edges` empty when over budget. It exports `MODULE_DIAGRAM_BUDGET`.
- Modify: `src/archkeel/render/assets/flow.js` `renderAtlas` (:2617). The over-budget branch reuses the existing empty-scene path (`alternative` notice, `layoutState`). It must not call `requestLayout`.
- Regenerate: runtime bundles
- Test: `tests/test_atlas_report.py`, `tests/test_report_renderer_units.py`

**Interfaces:**
- Consumes: Task 1 not required. The tasks are independent.
- Produces: `atlasModuleScene(level, viewMode)` returns `{..., overBudget: null | {modules, edges, budget}}`. When `overBudget` is set, `nodes` and `edges` are `[]` and `moduleOverview` is `true`. `root.dataset.layoutState === "skipped"` in that case.
- Notice copy (exact): `Diagram not drawn: {modules} modules and {edges} relationships exceed the diagram budget of {budget.modules} modules / {budget.edges} relationships. Open a component, search, or use Health check. All facts remain in the module list and architecture.json.`

- [ ] **Step 1: Write failing unit tests** in `test_report_renderer_units.py`:
  - `test_module_scene_over_budget_is_empty_and_counted`: an atlas level with 81 modules gives `overBudget.modules == 81` and `nodes == []`.
  - With 80 modules and 300 edges: `overBudget is None`.
  - With 80 modules and 301 edges: over budget.
  - Build the payload with a small helper `_atlas_level(module_count, edge_count)` in the test file. It follows the compact `ATLAS.modules/cells/levels` shape used at `report-scene.js:25-38`.
- [ ] **Step 2: Write failing browser test** `test_over_budget_module_level_skips_layout_and_keeps_navigation(tmp_path)`. Generate a temp Python repo with 81 modules (`m{i}.py` imports `m{i+1}`) and render it as in `_report_page`. Assert:
  - Goto `?content=modules`: the notice text matches the exact copy above, `.flow-canvas` is hidden, `data-layout-state="skipped"`, and the module list shows 81 entries.
  - `?content=modules&view=target` and `view=diff`: same notice. This covers Review Focus 2.
  - `?module=<id of m0>` opens the module detail in the inspector, with `data-layout-state="skipped"` and zero `.node[data-uml-id]` elements. This covers Review Focus 1.
  - Health check opens. This covers Review Focus 5.
  - Navigating to a component with ≤ 80 modules ends in `data-layout-state="ready"` and the notice is hidden. Use the existing `_nested_repository` for this part. This covers Review Focus 4.
- [ ] **Step 3: Run both, expect FAIL.**
- [ ] **Step 4: Implement** the budget check in `atlasModuleScene` (count before building node objects) and the `renderAtlas` branch. Update `.atlas-summary` so it states the totals.
- [ ] **Step 5: Regenerate and pass:** `make browser-runtime-generate`, both tests, then `make browser-runtime-check`, then the existing `tests/test_atlas_report.py` and `tests/test_uml_visual_acceptance.py`.
- [ ] **Step 6: Measure, not gate:** self report root "Modules" (146) now shows the notice. EE root "Modules" (1,174) reaches ready in < 1 s. Note the numbers in the commit body.
- [ ] **Step 7: Commit** `fix(report): skip module diagrams above the layout budget`

### Task 3: Verify and hand off

- [ ] `make check` (lint, typecheck, browser-architecture-check, tests)
- [ ] `git diff --stat origin/main -- src/archkeel/render/*.py src/archkeel/ir` is empty (payload unchanged)
- [ ] Push the branch; CI decides `ci-pr-report-check`.

## Out of scope (separate decisions)

- ELK in a Web Worker: helps responsiveness, not memory. Revisit only if a component under budget still blocks the UI for more than 1 s.
- Neighborhood view (selected module plus direct neighbors): add only if users still miss a navigation path after Task 2.
- `_literal_exports` duplicate (`check/validation/public_api.py` vs `ir/interfaces.py`, which differ on empty `__all__`), the CLI option-rule SPOT, and CI shard duplication: separate plans.
