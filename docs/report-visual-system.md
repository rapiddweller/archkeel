# Archkeel report visual system

## Purpose

Within five seconds, readers should see what passed, failed and remains unknown.
Show evidence, never an architecture score.

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

- Put the explorer after verdicts and before rule/violation lists. Section links
  jump to findings and limits; finding links reveal collapsed or filtered records.
  Each finding retains cited source and a copyable packet bound to commit, source
  digest and contract. Native disclosure and selection work without JavaScript;
  clipboard failure falls back to selection. Actual/Target Diff compares a snapshot
  with a contract; Check compares accepted and candidate revisions. Missing comparison
  never means no change. Human effectiveness needs the [review pilot](review-pilot.md).
- As-Is, Actual, Target and Diff share navigation while keeping evidence distinct.
  Actual retains every module, including unassigned ones. Target shows independent
  declarations, permissions and file intent. Diff retains findings, UNKNOWN,
  unmapped modules and absent targets. Empty scopes do not imply PASS. Missing
  counterparts offer nearest-scope navigation (AD-144); declared unowned modules
  stay visible under “Modules outside components”.
- Physical frames require every contained module to match a unique declared namespace.
  Only populated frames and ancestors appear. They add no target-only cards, edges
  or ranks. Declared cards with zero observed modules remain visible without proving
  existence. Folders are navigation groups, not components or inferred directories.
- Diagram, Structure and Review share breadcrumbs. Start with every group and connection
  at the level. Review lists violated/undecided connections before busy conforming ones;
  the optional matrix shows up to twelve high-traffic entries. Each view reports shown
  and total entries. Reset focus returns to all groups and components.
- Standard entities and relationships use the
  [shared UML model](architecture/uml-model-target.md). Class/interface compartments
  show fields, operations and visibility. Inheritance uses a solid line/hollow triangle;
  realization uses a dashed line/hollow triangle. Calls, imports and references remain
  distinct with original sites. Never infer inheritance, composition or a symbol kind
  from missing facts. Whole-module imports are `module`, stars are `star import`, and
  unresolved named imports are `unknown`.
- Details retains roles, responsibilities, typed ownership, public/planned selectors,
  rationale, decider, file inventories and layout permissions. Undeclared and explicitly
  empty intent remain distinct. Allowed children need not exist; file/API selectors
  invent no classes or calls. Global API intent retains independent provenance and
  excludes source-derived exposed types. `requires` means allowed imports, not mandatory
  calls. Repeated permissions keep separate IDs and actual endpoints.
- Diff puts differences first and collapses matched Core assessments. Endpoints use
  Core correspondences; ambiguous identities keep separate observed cards. Grouped edges
  retain every site and originating graph. Observed-only classes and operation graphs
  open in the same renderer; navigation retains origin and raw ID. Unassessed scopes
  say so. Unresolved/missing endpoints stay in Details without invented cards or PASS.
- Use one scene and renderer for metrics, layout, shapes, routes and emphasis. Projection
  supplies recorded IDs, kinds, labels, membership and relationships; the controller
  owns navigation and evidence. An outer package keeps its header without a redundant
  outline; nested boundaries remain. Interior views omit the parent card/containment
  lines because breadcrumbs identify the scope. Explicit relationships to lexical
  scopes can still draw those endpoints. Declared dependency ranks shape layout;
  cycles remain unranked.
- Select once to update Details; connection rows expose counts, rules and source sites.
  Enter, double-click or Open selected drills one level. Searchable declarations retain
  full responsibilities. Matching requires stable declaration ID, exact module/file
  identity or a unique package match; otherwise say no declaration matches.
  Fullscreen/Restore preserves explorer state.
- Hover/keyboard focus previews direct neighbors without moving cards or replacing
  selection. Leaving restores selection emphasis; touch selects directly. Connected
  cards/lines gain contrast and unrelated ones recede. Dimmed lines cannot intercept
  background clicks. Every hit area belongs to a visible element with drawn endpoints.
- Package headers use a compact role/name. Abbreviate measured overflow only; full
  identities remain accessible through pointer, keyboard, touch and Details. Bounded
  detours avoid header text when possible. Otherwise keep the edge and expose a separate
  renderer layout warning in its accessible label and Details. Architecture status stays
  unchanged. Legends wrap on narrow screens.
- Shared glyphs distinguish component tabs, package folders, module files, class
  compartments, interface circles and enums. Methods use `()`, functions `ƒ`.
  Text labels preserve meaning without color. Calls use blue, imports violet,
  references grey, construction teal and instance types cyan; lines, arrowheads and
  legend share tokens. Core FAIL/UNKNOWN styling takes priority.
- Cards use measured widths and individual content heights; row bounds, ports and
  obstacles share those measurements. Balance large unframed levels against viewport
  proportions. Class overviews start with field/method counts; optional member previews
  retain every card, edge and site. Full signatures remain in Details/opened classes.
  Preview changes recalculate positions without changing scope or evidence.
- Focus shows one exact entity and direct incoming/outgoing neighbors, retaining violated
  edges. Show subset and complete-level counts. Focused Fit stays at least 100%; larger
  views scroll. Relationship and element-kind filters share scene filtering across all
  views. Hidden edges have no hit areas; edges need two visible endpoints. Details and
  Core status remain complete. Reset restores all identities and connections.
- One router allocates ordered ports and collision-checked routes in every view.
  Reciprocal edges share lane allocation. Keep fixed readable arrowheads and solid
  terminal stems. Browser tests inspect actual cyclic, recursive and own-model SVG
  geometry. Dense graphs can still cross or need filtering/manual arrangement; filtering
  and routing never change architecture evidence. Full Fit may shrink text below reading
  size; Reset restores 100%, while drill-down and Details retain readable content.
- Long name lists and facade measurements use native disclosures with complete counts
  and evidence accessible without JavaScript.
- Component-level diagrams use UML boxes, one provided-interface circle and declared
  `requires` sockets. Only a conforming observed `through` edge gets an assembly marker.
  Unrestricted or undecided edges cannot imply a specific interface connection.
- Unassigned modules form a navigation-only group with no component verdict/permission.
  Package folders retain openable initializers and every module, including symbol-free
  ones. Group edges sum sites and retain rule IDs; same-folder edges reappear on opening.
  Breadcrumbs return through component, package and module levels.
- External imports governed by `external_dependency_scope` use one `«library»` card per
  dependency and dashed `«use»` edges. Multiple scope rules remain inspectable on that
  card, including all violating IDs.
- Start at 100% zoom and threshold zero in a bounded native scroll area. Zoom and Fit
  are explicit. Threshold hides only non-violating edges and reports shown/total counts.
  Arrange resets positions while retaining focus, threshold and zoom; Resize retains zoom.
  Hide scrollbar tracks. Background drag pans without moving cards or selection; wheel
  and keyboard remain available. Narrow toolbars/breadcrumbs wrap and filters/legend use
  native disclosures.
- Import weights count source sites; module calls/references are symbol-use edges.
  Conforming edges are solid teal; violations are dashed red with rule IDs. Inside
  edges stay observed unless an inside rule decides them. No finding does not prove
  conformance. Rule chips take priority over weights; if sampled positions cannot clear
  cards, headers and other chips, use a selectable gutter row naming endpoints/rules.
- Drilled scopes retain connected outside neighbors as dashed `«outside»` cards. Exact
  crossings retain their own counts, rules and source samples; no other crossing's finding
  is copied. Local counts exclude outside cards. Opening one records the original scope
  for Back, adding no ownership or permission (AD-180).
- Switching from Target restores the observed legend from actual edge states; the overview
  lists the five heaviest connections. Structure and Review support keyboard navigation.
  Without script, communication tables and inventories stay readable; interactive controls
  stay hidden. Cross-repository level 1 waits for observed interfaces.
- Use semantic UML glyphs, without gradients, glow, shadows or decorative icons.

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
Terminal exports use SVG glyph scaling to keep measured columns aligned with fallback fonts.
Browser acceptance includes a dragged no-route case that retains inventory and evidence
while Details exposes a layout warning. Static HTML assertions cannot prove browser behavior.

## Accessibility and print

- All interactive elements need a visible teal focus ring.
- Status must survive grayscale printing through symbol, label, and border.
- Tables scroll horizontally below 760 px; cards become a single column.
- Print switches to white surfaces and the light logo while retaining semantic
  status accents.
- Do not place body text in lime, teal, red, or amber. Those colors are for
  short labels, links, evidence values, and state indicators.

## Non-negotiable rules

Keep exact evidence and explicit UNKNOWN, independent verdicts, accessible status,
and semantic notation. Apply the rules above consistently. Limit each evidence row
to one accent color unless two compared states require separate colors.

## Implementation assets

- `src/archkeel/render/assets/archkeel-report.css`: tokens and report components.
- `src/archkeel/render/assets/archkeel-logo-dark.svg`: dark-header logo.
- `src/archkeel/render/assets/archkeel-logo-light.svg`: print/light logo.
- `src/archkeel/render/assets/archkeel-mark.svg`: compact mark.
