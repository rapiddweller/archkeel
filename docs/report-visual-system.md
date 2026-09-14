# Archkeel report visual system

## Purpose

The report must make one thing obvious within five seconds: what Archkeel
could verify, what failed, and what remains unknown. It is an evidence surface,
not a dashboard and not a scorecard.

## Brand idea

The mark combines two code brackets with a central keel. The brackets represent
the observed code structure. The keel represents the locked architecture that
keeps the candidate aligned.

Use the logo as follows:

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

Verdict colors are functional data colors, not brand decoration. Keep them
inside verdict chips, a 3–4 px border, or a chart series. They should occupy
less than 10% of a page.

| Verdict | Hex | Symbol | Meaning |
| --- | --- | --- | --- |
| `PASS` | `#C5F82A` | `✓` | The claim was checked and holds |
| `FAIL` | `#FF6B6B` | `×` | The claim was checked and rejected |
| `UNVERIFIABLE` | `#F4C95D` | `?` | Required evidence is missing or invalid |
| `INFO` | `#5EEAD4` | `i` | Context that does not change the verdict |

Never communicate a verdict through color alone. Always render the symbol,
verdict word, and one-sentence reason. `UNVERIFIABLE` must never inherit pass
styling.

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
2. Decision banner: pass, reject, or unverifiable. This is an exit decision,
   not a score.
3. The report verdict cards, always in contract order. Architecture reports show three;
   check reports add `git_predicate` and `host_order` for five total verdicts.
4. Evidence that caused a failure or uncertainty.
5. Complete findings, raw measurements, fingerprints, and diagnostics.
6. Reproduction metadata and analyzer/runtime versions.

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

### Diagnostics

Render the four contract fields without renaming them:

```text
kind · subject · unknown_claim · remedy
```

The remedy is actionable and comes last. Diagnostics use the unknown color
unless the check has already classified them as a failure.

### Architecture graph

- Components: near-black cards with subtle borders.
- Accepted edges: lime.
- Candidate or declared edges: teal.
- Rejected edges: red and dashed, with a textual violation code.
- Unknown edges: amber dotted line.
- Straight right-angle connectors only. No gradients, glow, shadows, or
  decorative icons.

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
at 1440 × 1000 and case A at 375 × 2400. Firefox is the reference browser because
headless Chrome has produced incomplete captures on the current macOS compositor.
The target is intentionally excluded from `make check` because it requires a local
browser. Use a new output directory for each run.

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
