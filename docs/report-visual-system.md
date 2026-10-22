# Archkeel report visual system

Make FAIL and UNKNOWN evidence easy to find. Never summarize independent verdicts
as an architecture score. The banner follows Core verdicts and receipts, not exit
code alone; a confirmed violation remains FAIL alongside uncertainty.

## Render evidence

The report opens with one verdict line, then the ranked findings, then the explorer
([AD-258](architecture/decisions/ad-258-report-opens-with-ranked-findings.md)). The line
shows the badge, the declared-rules verdict, the PASS and UNKNOWN rule counts, the
agent-decision ratio, the source observation and the short git hash; the full hash stays
in the collapsed Snapshot section. The list is an ordered list rendered without JavaScript:
rank, title, size, up to three locations and one sentence, each linking into the explorer
with its own routes. The terminal summary and `--json` carry the same list; no script ranks
findings. The static rule cards and the reading guide are gone from this page.

ArchQ Explorer is embedded in the report. Fullscreen expands the same explorer;
Restore returns to the report without losing the current view. Search (`Ctrl/⌘+K` or `/`) finds
components, modules and rules. Hover traces dependencies; `Ctrl/⌘`+wheel zooms
at the pointer. Health check opens findings and the import matrix. Snapshot provenance
and the complete JSON link remain in the report and in Health check.
Perspectives show recorded authorship, layer or evidence without changing verdicts.
Share copies the current link or Mermaid, or downloads a standalone SVG.

As-Is, Target and Diff use the shared [graph boundary](architecture/render-target.md).
Target shows independent intent; Diff uses Core correspondences. Rendering must
not infer ownership, endpoints, realization or PASS. Permissions are declarations,
not passed checks. Missing comparison is not no change.

Atlas component positions are shared across As-Is, Target and Diff within a
report snapshot; changed source relationships may change that shared layout.
Target edges, labels and statuses remain authored-only.

The unselected fact sheet summarizes declared and applied boundary permissions.
Selecting a component, module or member shows the relevant records for that scope.
The complete audit groups records by rule and builds summaries in batches of 20;
opening a record reveals its selector, rationale, provenance and source navigation.
Deep links open the exact record even beyond the first batch. These disclosures
leave the complete canonical audit unchanged; permission counts do not imply PASS.

Health check constructs the module matrix on first open and reuses it until the
scene changes. Native module lists construct links when expanded. Collapsed
disclosures defer DOM work while keeping counts, verdicts and offline navigation.
Opening a large matrix still builds all its cells; it is not virtualized.

Structure overview shows every measured component's module, internal-edge,
incoming, outgoing and unresolved-call counts, with links to its canonical route.
Top-level component and cross-component edge counts provide separate context.
Size alone supplies no review candidate, boundary recommendation or verdict.
Missing edge evidence is `n/a`; known module counts remain visible. The legacy
evidence report also retains package measurements. Canonical recorded size claims
remain compatible. Separate Used elsewhere/Hub hint calibration remains open in
[#384](https://github.com/rapiddweller/archkeel/issues/384).

Show verdict word, symbol and reason; color alone is insufficient. Baselined
violations remain visibly FAIL with known-debt status. Filters and Focus retain
complete counts and evidence. An empty graph says no matching edges at this level
and points to findings. Every hit area needs a visible element and endpoints.

Keep source locations, identities and provenance copyable. Details retains full
values when labels truncate. Renderer routing warnings stay separate from
architecture status. Without JavaScript, findings and inventories remain readable.
Keyboard focus, narrow layouts and grayscale printing must preserve meaning.

[CSS and assets](../src/archkeel/render/assets/) own tokens, typography, logos and
geometry. Use them rather than copying a second specification here.

## Verify a renderer change

```bash
make browser-install
make report-browser OUTPUT=test-artifacts/report-browser
```

Use a fresh output directory. The pinned Chromium lane exercises nested
navigation, As-Is/Target/Diff, filters and mobile layouts, saving screenshots and
traces. Review images and captions before copying canonical PNGs to `docs/assets`.
Static HTML assertions do not prove browser behavior.

Terminal captures use `make demo OUTPUT=<fresh-directory>` followed by
`uv run --locked python -m tools.terminal_svg <fresh-directory>`.
The older `make demo-screenshots` target requires Firefox and stays outside
`make check`. Human review effectiveness needs the [pilot](review-pilot.md).
