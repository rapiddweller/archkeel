# Readable target hierarchy — #224

Astra approved this design under delegated architecture authority. Alex must still approve the rendered candidate before its implementation PR merges.

## Scope

Use the existing explorer, declarations and navigation. Do not change CE ownership, the canonical semantic tree, verdicts, IDs, graph keys or view matching. No new dependency, view tab, architecture model or `exact_modules` capability. `packages` retains dotted-prefix ownership.

## Projection

- Add presentation-only `containers` to `target_diagrams`: `{id, parent, members, scope}`. IDs are existing `layout:<rule-id>` IDs; members are existing node IDs.
- Add component `placement: {status, scopes, container}`. Status is `declared`, `inferred`, `multiple`, `ambiguous` or `unmapped`. Container is an ID or null.
- Derive placement only from concrete declared namespace/package strings and a declared `root_layout` chain. Never use observed modules, prose, labels or substring guesses. Unsupported selectors remain unmapped.
- Use the deepest unambiguous container covering every scope. Multiple scopes may share one frame only when they resolve to that frame. Otherwise retain one explicit unplaced card with all scopes and its reason; do not duplicate a semantic component.
- Fold redundant single-component/same-namespace frames into the component's placement details. Keep every declaration navigable, including folded layouts, physical-only children, module inventory and modules outside components, with counts.
- CE root has ten semantic owners. Its `datamimic_ce` frame contains an expanded `engine` frame holding the existing DSL, IO and Runtime cards. Engine is not a new semantic owner.
- Target details expose exact `public`, `requires.through`, rationale and provenance. Distinguish absent/null and explicitly empty interfaces. UML circles/sockets denote declarations, not observed assembly or PASS.

## Layout and interaction

- Rank original semantic `requires` edges before framing, with stdlib `graphlib.TopologicalSorter`: providers are their consumers' prerequisites. Sort ready nodes; compute dependency depth as 0 without prerequisites, otherwise 1 + maximum prerequisite depth. After processing, visual rank is `max_depth - depth`; tie-break by stable ID. Dependents precede dependencies. Containment is not a dependency or architectural layer.
- On `CycleError`, drain acyclic ready nodes and retain every residual node/edge in an unranked band: “Dependency order unresolved: cycle or dependency on a cycle.” Residual does not imply cyclic. Self-loops remain inspectable. Emit `dependency_rank: integer | null`; null is not an UNKNOWN verdict.
- Physical frames are disjoint horizontal lanes, semantic ranks vertical. Nested frames refine lanes. Never collapse frames into rank vertices: Runtime → Domains → IO must not manufacture an Engine/Domains cycle. Use native scrolling rather than unreadable automatic Fit.
- Frame headers enter existing layout graphs; placed component cards enter existing semantic graphs. Root → engine → runtime → tasks, direct root → runtime and legacy inventory navigation work. Label physical breadcrumb steps without asserting semantic ownership.
- Preserve #223 unmatched-return context, selected identity and physical navigation route across Actual/Target/Diff. Never substitute an unmatched folder.
- Expand only the explorer beyond the prose width cap, using viewport width minus page gutters and available height. Default graph zoom is 100%; names ≥14 CSS px, responsibility previews ≥12 CSS px. Fit is explicit.
- Details start collapsed until selection. A keyboard-accessible Details toggle uses `aria-expanded` and `aria-controls`; toggling preserves path, selection, zoom, positions and scroll anchor. Resize must not Arrange/Fit. Preserve preference on navigation; deliberate selection may reopen.
- Full names, responsibilities and interfaces are accessible on selection, not hover alone. Keep an explicit keyboard-accessible Open action. Existing Diagram/Structure/Review and filters retain their meaning.
- Preserve `[data-target-node]`/`[data-target-edge]`. Add `[data-target-container="layout:<id>"]`, `[data-target-container-open="layout:<id>"]`, `data-placement-status` and `[data-flow-details-toggle]`. Show current-scope shown/total counts.

## Acceptance

- Declaration-only projection without observed modules; recursive layouts; multi/ambiguous/unmapped scopes; disconnected nodes; self-cycle and two-node cycle plus dependent; absent/empty/declared interfaces; reordered-input determinism; complete inventory.
- Chromium at 1440×1000 and 1856×1336 CSS pixels, initial zoom 100%: readable non-overlapping frames/cards, all nodes reachable by scrolling, reversible Details toggle and pointer/keyboard access.
- Real CE root ten owners → runtime eight children → tasks seven children → generate → workers, plus physical engine navigation. Exact view identity round trips, missing declarations and UNKNOWN remain explicit.
- Focused tests, `make report-browser`, `make check`, build/smokes and self-observation when stale. Capture real CE root/runtime/tasks at both sizes; those images are QA evidence, not approved documentation.

## Documentation and merge

The implementation PR includes an AD under 70 lines, architecture index, roadmap, updated behavior text, release notes and runnable positive/negative demos.

Alex's report approval → implementation PR merge → one bundled refresh of current README, documentation and demo screenshots from the merged revision → release 0.8.2. Alex's latest instruction makes current screenshots a release prerequisite, not a deferred follow-up after release. Inspect every README image, refresh every current report/terminal screenshot, and verify captions, counts and links. Product screenshots show Actual, Target and Diff controls, readable content, useful crops and real declared hierarchy; do not fake the UI. Static artwork and historical release evidence remain unchanged when still accurate. Functional green does not close #224 or replace visual approval.
