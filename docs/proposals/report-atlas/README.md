# Report atlas mockup

Clickable proposal for #355: explore the As-is against the Target. Download
`archkeel-atlas.html` and open it in a browser. It is self-contained; only fonts load from
Google Fonts.

The data is real Archkeel 0.9.0 output, not invented:

| Repository | Commit | Contract |
|---|---|---|
| archkeel | b6636e8 | this repository |
| DATAMIMIC CE | [b55980c](https://github.com/rapiddweller/datamimic/commit/b55980c3b280e5c8c97abd177035676ffd51dec6) | draft PR rapiddweller/datamimic#274 |

Both were produced with `archkeel report --output <dir>/architecture.json --json`.

`build_explore.py` turns one report into the dataset the page embeds. It reads
`architecture.json`, `architecture.report.html` and the `--json` output. It is the
reference for the hint rules in #355. The product computes them in Core, not in the
renderer.

Proposals, not report data:
- the layer chips;
- the `typescript-adapter` card;
- the Interfaces & seams tab (#356);
- "Simulate violation".

| Screenshot | Shows |
|---|---|
| `screenshots/1-map-asis.png` | Map in the As-is lens with weights; fact sheet |
| `screenshots/2-diff-check.png` | Diff lens inside `check`: the one allowed but unused dependency |
| `screenshots/3-explore-ir.png` | Hints and module matrix for `ir` |
| `screenshots/4-module-sheet.png` | Module sheet: the owner's responsibility next to observed use |
| `screenshots/5-explore-ce.png` | The same view at CE scale: 492 modules |

This directory is not a product file and no test covers it. Delete it once #355 lands.
