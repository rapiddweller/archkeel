# Archkeel report visual system

## Purpose

The report must make one thing obvious within five seconds: what Archkeel
could verify, what failed, and what remains unknown. It is an evidence surface,
not a dashboard and not a scorecard.

## Brand idea

The mark combines two code brackets with a central keel. The brackets represent
the observed code structure. The keel represents the locked architecture that
keeps the candidate aligned.

Use the logo as follows (paths relative to `src/archkeel/render/`):

| Context | Asset |
| --- | --- |
| Dark HTML header | `assets/archkeel-logo-dark.svg` |
| White or printed report | `assets/archkeel-logo-light.svg` |
| Favicon, compact navigation, status page | `assets/archkeel-mark.svg` |
| Raster fallback | `assets/archkeel-mark.png` |

Minimum mark size: 24 px. Minimum horizontal-logo height: 28 px. Preserve clear
space equal to the width of the central keel stroke. Do not rotate, stretch,
outline, recolor, or place the mark inside another badge.

## Color system

### Brand colors

| Token | Hex | Role |
| --- | --- | --- |
| `lime` | `#C5F82A` | Primary identity, accepted architecture, focus |
| `teal` | `#5EEAD4` | Candidate and declaration evidence, links |
| `black` | `#000000` | Report and header background |
| `surface` | `#141414` | Cards and tables |
| `surface-raised` | `#1F1F1F` | Hover and nested surfaces |
| `border` | `#2A2A28` | Dividers and card outlines |
| `text` | `#E8E8E2` | Primary text on dark surfaces |
| `muted` | `#8A8A84` | Metadata and secondary labels |

### Verdict colors

Verdict colors are functional data colors, not brand decoration. Use them for
status labels, evidence rows and graph relationships, not ordinary prose.

| Verdict | Hex | Symbol | Meaning |
| --- | --- | --- | --- |
| `PASS` | `#5EEAD4` | `✓` | The claim was checked and holds |
| `FAIL` | `#FF6B6B` | `×` | The claim was checked and rejected |
| `NOT CHECKED` | `#F4C95D` | `?` | A required verdict is `UNKNOWN`; evidence or rule evaluation is incomplete |
| `INFO` | `#5EEAD4` | `i` | Context that does not change the verdict |

Never communicate a verdict through color alone. Always render the symbol,
verdict word, and one-sentence reason. `NOT CHECKED` must never inherit pass
styling.

Rule tables use teal for checked PASS, red for FAIL, amber for UNKNOWN, and gray
for DECLARATION. A permission is not a passed check. New violation rows are red;
fully baselined fingerprints are gray with a KNOWN badge and a red FAIL marker.
Mixed known/new occurrences keep their group counts without inventing line identity.

## State mapping

Use these colors consistently when comparing repository states:

| State | Color |
| --- | --- |
| Accepted or locked state | Lime |
| Published expectation | Teal |
| Candidate observation | Off-white |
| Regression or rejected edge | Fail red |
| Missing evidence | Unknown amber |
| Historical or inactive value | Muted gray |

Do not reuse red for ordinary negative deltas. A reduction can be good. Apply
red only when the contract classifies the change as a regression or failure.

## Typography

- UI and explanation: `Inter`, then the system sans-serif stack.
- Commits, paths, fingerprints, ratios, counters, and diagnostics: system
  monospace.
- Headings: weight 500. Body: weight 400.
- Sentence case for headings. Uppercase is reserved for short machine-state
  labels such as `PASS` and `FAIL`.
- Minimum sizes: 14 px body, 12 px metadata, 11 px machine labels.

## Report hierarchy

1. Logo, repository, candidate SHA, accepted SHA when available, and source digest.
2. Decision banner: pass, reject, or not checked. It follows verdicts and per-rule evidence,
   not the exit code alone, and is not a score. An UNKNOWN non-declaration rule keeps the
   aggregate verdict UNKNOWN; a known violation remains FAIL.
3. The report verdict cards, always in contract order. Architecture reports show three;
   check reports add `git_predicate` and `host_order` for five total verdicts.
4. Architecture explorer.
5. Evidence that caused a failure or uncertainty.
6. Complete findings, raw measurements, fingerprints, and diagnostics. A report with violations
   offers the AD-75 focus control at the violation table; it may hide secondary detail, never the
   verdicts, failures or known unknowns.
7. Reproduction metadata and analyzer/runtime versions.

The three verdicts must never be averaged into one health number. A gauge such
as “architecture score 84” destroys the contract semantics.

## Components

### Verdict card

- One 3 px semantic top border.
- Verdict chip with symbol and full word.
- Contract key in monospace.
- One direct reason. No marketing explanation.
- Evidence count or diagnostic link where relevant.

### Evidence table

- Put accepted and candidate values in adjacent columns.
- Use raw fractions (`0/2 → 1/1`), not rounded percentages alone.
- Right-align numeric values.
- Highlight only the value that caused the verdict.
- Preserve full values in copyable text, even if the visual column truncates.

### Violation focus

- Use one native checkbox. Reveal it only after its script runs, so no-JavaScript output remains
  complete.
- `Violations only` changes the report view, not the evidence. `Violating edges only` explicitly
  describes the narrower graph operation.
- An empty filtered graph says “No violating edges at this level” and points to the table; it never
  says that the whole report has no violations.

### Diagnostics

Render the four contract fields without renaming them:

```text
kind · subject · unknown_claim · remedy
```

The remedy is actionable and comes last. Diagnostics use the unknown color
unless the check has already classified them as a failure.

### Component dependencies

- Verdicts precede exploration; findings and analysis limits follow it. Section links provide direct access.
  Finding links reveal collapsed or filtered records. Each finding retains all cited source evidence
  and a copyable packet bound to the analyzed commit, source digest and contract. Native disclosure
  and text selection work without JavaScript; clipboard failure falls back to selection.
  Actual/Target Diff compares code with a contract; the check page compares accepted and candidate
  states. An unavailable comparison must not claim that no changes occurred (AD-130).
  Human effectiveness is tested with the [review pilot](review-pilot.md).
- The observed flow has three views at the same breadcrumb level: focused UML diagram to explain
  interfaces, physical structure map to find modules, and a connection-first review queue.
  The diagram starts with every group and connection at the current level. Selecting a focus
  keeps every direct neighbor and all violated edges, not an arbitrary number of neighbors.
  Review shows every violated or undecided connection before the busiest conforming ones;
  the matrix is optional and shows up to twelve high-traffic entries. Focus can be reset to
  “All components and groups”; each view reports shown and total entries for its current scope.
- As-Is, Actual, Target, and Diff share one explorer shell and navigation contract while keeping
  their evidence distinct. Actual lists every observed module, including unassigned ones. Target shows
  declared components, package scopes, physical layout, allowed children, and requirements; its
  edges are declarations, not import evidence or conformance claims. Diff retains violations,
  UNKNOWN evidence, unmapped modules, and declared targets absent from the observation. Folder
  grouping does not silently drop entries. Diff retains nested scope and filters recorded evidence;
  empty scopes do not imply PASS. Missing counterparts offer explicit nearest-scope navigation
  (AD-144). Declared modules outside component ownership remain
  visible under “Modules outside components”.
- As-Is's physical frames require every actual module in a card to match the uniquely
  resolved declared namespace. Only populated frames and ancestors appear; they do not add
  target-only cards, edges, or ranks to the observed graph. Existing declared cards with zero
  observed modules remain visible but never prove observed existence or populate frames.
- The explorer follows Independent verdicts, before rule and violation lists.
- As-Is modules and Contract 2.2 Target/Diff draw standard graph entities (AD-160).
- Root Contract 2.2 file inventories and layout permissions appear in expandable details
  (AD-162). Allowed children are permissions; file intent defines no classes or calls.
  Nested explicit UML keeps component parents and labels; Details scopes inventories and
  layout permissions to their declaring component (AD-163). Names do not define hierarchy.
  `requires` edges name allowed component imports (AD-164). Details retains each selector,
  rationale and decider; these permissions are not required calls or UML comparison verdicts.
  Class/interface compartments show attributes, operations and visibility. Inheritance uses a
  solid line with a hollow triangle; realization uses a dashed line with a hollow triangle.
  Calls, imports and references retain separate kinds and source sites. Diff shows Core's
  recorded statuses as text, puts differences first and collapses matched assessments.
  Unlisted relationships use Core's typed correspondences (AD-165). Ambiguous endpoints keep
  separate observed cards. Grouped edges retain every site and the graph that owns its IDs.
  Observed-only classes and operation call graphs open through the same renderer (AD-166).
  Navigation retains origin and raw identity. Unassessed scopes say so; unresolved sites stay
  inspectable without invented endpoint cards.
  Missing endpoints remain inspectable evidence; they never create invisible clickable cards.
  Component cards show their declared role. Details retains typed ownership and published/planned
  API selectors (AD-161), separate from language visibility. Undeclared and explicitly empty
  APIs remain distinguishable. A selector does not invent a class or a call.
  Global published API selectors and their provenance appear in root Target/Diff
  Details (AD-168). Source-derived exposed types stay outside Target intent.
  Legacy component details and import permissions also read the authenticated graph (AD-169).
  Repeated permissions retain separate IDs and real endpoint cards. Permission is not execution.
- As-Is and Target use one plain render scene and one renderer for card metrics, package layout,
  UML shapes, routing and relationship emphasis. Source projections supply IDs, kinds, labels,
  metadata, package memberships and typed relationships; the controller owns navigation/evidence.
  Component, package, file artifact and observed class symbols carry semantic meaning.
  Dependencies never imply inheritance or composition; declared interfaces remain in Details.
  A single outer package keeps its header without a redundant outline; nested boundaries remain.
- As-Is and Target cards keep names, kind and counts; complete responsibilities remain in Details.
  Target uses UML component and package symbols, blue declarations and dashed dependency arrows.
  Arrowheads keep a readable fixed size and a solid terminal stem in both graphs.
  A component's interior omits its parent card and containment lines; its breadcrumb owns the scope.
  An explicit relationship to a lexical scope may draw its endpoint card in the normal layout.
  Declared dependency levels shape its vertical layout; cycles stay explicitly unranked.
  Hover or keyboard focus previews direct neighbors without moving cards or replacing the pinned
  selection. Leaving the preview restores selection emphasis. Touch selects directly.
  Connected cards and lines gain contrast; unrelated cards and lines recede.
  Dimmed lines cannot intercept background clicks. Every hit path has two drawn endpoints.
- Select once to open and update Details. Incoming and outgoing rows select the connection and
  expose its counts, rules and source locations. Enter, double-click, or Open selected drills one level. The shared
  Details pane and searchable declaration list expose complete declared responsibilities in every
  view. A correspondence requires stable declaration identity, exact module-file identity, or a
  unique package match; otherwise Details says no declaration matches. This is target information,
  not observed behavior. Fullscreen and Restore preserve the current explorer state.
- Package headers use a compact role and name. Abbreviate only measured overflow, with the full
  identity available in Details by pointer, keyboard and touch. Relationship paths stay visibly
  clear of header text when a bounded detour exists. If not, keep the relationship and expose a
  renderer layout warning in its accessible label and selected Details; architecture status is
  unchanged. Keep the legend compact, allowing wrapped rows on narrow screens.
- Never infer a symbol kind from a missing definition. A whole-module import is `module`, a star
  import is `star import`, and an unresolved named import is `unknown`, not `constant`.
- Shared UML cards distinguish component tabs, package folders, module files, class compartments,
  interface circles and enumeration compartments. Operations show `()` for methods and `ƒ` for
  functions. Type labels retain the meaning when colors cannot be seen.
  Calls use blue, imports violet, references grey, construction teal and instance types cyan.
  The line, arrowhead and legend share one color token. Core FAIL/UNKNOWN takes priority.
  Measured card widths keep ordinary operation names on one line; full signatures stay in Details.
  Each card uses its own content height. Rows reserve the tallest card in that row;
  arrow ports and obstacles use the same measured bounds. Large unframed levels use
  more columns to balance the overview against the viewport's aspect ratio.
  Class overviews start with field and method counts. Member previews can reveal compact
  attribute and operation compartments. Both modes retain every card, relationship and
  source site. Full signatures stay in Details and the opened class; preview changes
  recalculate card positions without changing navigation or architecture evidence.
  Focus draws one exact entity and its direct incoming/outgoing neighbors. Counts show
  the subset and complete level; Reset filters restores all elements and connections.
  Automatic fit keeps focused views at least at 100% zoom; larger views scroll.
  Details and Core status retain complete evidence. Hover does not change the layout.
  The UML legend selects one relationship kind or all kinds. It shows complete-level
  counts; the filter status names the visible subset. Hidden edges have no hit areas.
  Diff retains its complete Core status even when a filter hides failed relationships.
  Element kind selects the standard graph's kinds in the same scene filter.
  Connections require two visible endpoints; Reset restores all identities.
  Complete counts, Details, Core status and navigation remain intact (AD-177).
  Dependencies use ordered ports and one collision-checked router in every view.
  Incoming and outgoing edges share one port allocation per card side.
  Reciprocal edges share one row-pair lane allocation. Detours prefer free straight stretches
  before shorter paths; their arrival heights keep final rails separate. Outer targets get
  earlier lanes to reduce crossings within one caller's outgoing connections. Cyclic, recursive
  and own-model browser tests check the actual SVG geometry.
  A remaining shared stretch triggers a second search with more intermediate
  lanes and arrival heights inside the existing row gap. Other routes keep the
  first search. Retries require measured cards to fit within the canvas area;
  larger levels need filtering. No architectural evidence or status changes.
  Dense graphs still require visual review; crossings can remain.
  Unfiltered Fit overview includes every card. It may reduce text below reading size
  in large levels;
  Reset returns to 100%, and drill-down or Details exposes readable content.
- Long lists of imported names and facade measurements use native disclosure controls. The
  summary keeps counts visible and the complete evidence accessible without JavaScript.
- Level 2 uses UML component boxes. A circle marks a declared provided interface; a socket
  marks declared `requires`. Only a conforming observed edge with `through` gets an assembly
  marker. An unrestricted or undecided edge must not imply a specific interface connection.
- Modules with no unique declared owner appear in an “Unassigned modules” navigation-only group.
  It is not a component and carries no component-level verdict or permission.
- Level 3 groups physical subpackages as folders, not new semantic components. Package
  initializers stay openable module cards, including import-only initializers; folder navigation
  reaches every observed module, including those without symbols or a unique owner. Group edges
  sum import locations and preserve rule ids; hidden same-folder edges reappear when the folder
  opens.
- One provided interface marker per component keeps large APIs legible; the inspector expands
  the exact entries. Breadcrumbs return through component, package, and module levels.
- An observed import governed by `external_dependency_scope` draws a `«library»` card and
  a dashed `«use»` dependency. One card represents each external dependency even when multiple
  scope rules name it; all rule details and violating rule ids stay inspectable.
- Start at 100% zoom and threshold zero. A bounded native scroll area keeps labels readable;
  opening a large level must not silently shrink it. Zoom and Fit are explicit controls.
  A chosen threshold hides only non-violating edges, with shown/total counts beside it.
  Arrange resets card positions, not focus, threshold or zoom. Resize preserves the chosen zoom.
  The explorer has no visible scrollbar tracks. Dragging empty diagram background pans without
  moving cards or replacing the selection; wheel and keyboard navigation remain available.
  Toolbars and breadcrumbs wrap; narrow screens place filters and the legend in native disclosures.
- Import edges carry their observed import-location counts. Module call/reference edges are marked
  as symbol-use relationships, not import locations. A conforming edge is solid teal; a violated
  edge is dashed red with a chip naming the rule id.
- Inside edges stay observed unless an inside rule decides them; absence of a finding alone is
  not conformance.
- Drilled component and package diagrams retain directly connected outside neighbors as dashed
  `«outside»` cards. Exact module crossings preserve import counts, rule ids and source samples;
  another crossing's violation is not copied. Local module counts exclude outside cards. Opening
  a neighbor records the original scope for Back. This adds no boundary or permission (AD-180).
- Rule chips take priority over weight badges. Measured chips avoid cards, frame headers and
  other chips; when none of
  the sampled positions fits, a selectable gutter row names the source, target and rule summary.
  Dense levels can still need filtering or manual arrangement.
- Switching from Target restores the observed legend. The legend is drawn from the same edge states that style the graph, and the overview lists the
  five heaviest connections.
- Structure and Review work by keyboard as well as pointer. Without script, the component
  communication table and nested inventory remain readable; interactive flow controls stay hidden.
- Level 1 is not drawn until the observation can state cross-repository interfaces.
- No gradients, glow, shadows or decorative icons; the UML glyph is semantic notation.

## Shared report geometry

Architecture and check reports use the same header spacing, typography, card
height, card padding, and section rhythm. Check reports use five columns on wide
screens because they expose five independent verdicts. Both report types collapse
to one column below 760 px.

## Reproducible demo captures

Run from a clean checkout with Firefox available:

```bash
make demo-screenshots OUTPUT="$(mktemp -d)"
```

The command reproduces demo cases A, B, and C, then captures each check report
at 1440 × 1000 and case A at 375 × 2400. This older capture target requires Firefox
and remains outside `make check`.

For interactive report acceptance, use the same pinned Playwright/Chromium lane as CI:

```bash
make browser-install
make report-browser OUTPUT=test-artifacts/report-browser
```

It replays synthetic catalog fixtures, exercises nested navigation, Actual/Target/Diff at desktop
and mobile width, and report filters, then saves screenshots and traces. Use a new output
directory for each run. It writes the eight README report PNGs into that directory, not
`docs/assets`. Review each image and its caption before copying the canonical PNGs into
`docs/assets`. Repeat the captures after every renderer change; an earlier green run does not
verify the new images.
For the terminal SVGs, run `make demo OUTPUT=<new-directory>` and
`uv run --locked python -m tools.terminal_svg <new-directory>`; copy the reviewed exports too.
The 0.8.2 PNG refresh uses `PLAYWRIGHT_CHANNEL=chromium` with the existing capture command.
Terminal exports use SVG glyph scaling to keep measured columns aligned with fallback fonts.
Independent browser tests cover a native dragged no-route case: complete inventory and evidence
stay unchanged, and selected Details exposes the separate warning. These checks are
separate from the Python gate; static HTML assertions alone do not prove browser behavior.

## Accessibility and print

- All interactive elements need a visible teal focus ring.
- Status must survive grayscale printing through symbol, label, and border.
- Tables scroll horizontally below 760 px; cards become a single column.
- Print switches to white surfaces and the light logo while retaining semantic
  status accents.
- Do not place body text in lime, teal, red, or amber. Those colors are for
  short labels, links, evidence values, and state indicators.

## Non-negotiable rules

- No single architecture score.
- No green fallback when evidence is incomplete.
- No verdict represented only by color.
- No rounded percentages when an exact ratio exists.
- No gradients, glow, drop shadows, illustrations, or stock imagery inside the
  report.
- No repeated hero graphic. The report uses the compact logo and evidence.
- No more than one accent color per evidence row, unless two compared states
  require it.

## Implementation assets

- `src/archkeel/render/assets/archkeel-report.css`: tokens and report components.
- `src/archkeel/render/assets/archkeel-logo-dark.svg`: dark-header logo.
- `src/archkeel/render/assets/archkeel-logo-light.svg`: print/light logo.
- `src/archkeel/render/assets/archkeel-mark.svg`: compact mark.
