# Archkeel report visual system

Make FAIL and UNKNOWN evidence easy to find. Never summarize independent verdicts
as an architecture score. The banner follows Core verdicts and receipts, not exit
code alone; a confirmed violation remains FAIL alongside uncertainty.

## Render evidence

As-Is, Target and Diff use the shared [graph boundary](architecture/render-target.md).
Target shows independent intent; Diff uses Core correspondences. Rendering must
not infer ownership, endpoints, realization or PASS. Permissions are declarations,
not passed checks. Missing comparison is not no change.

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
