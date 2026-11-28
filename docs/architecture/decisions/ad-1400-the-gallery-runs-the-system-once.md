# AD-1400: The gallery runs the system once

Status: accepted. Follows AD-1350 (one core run for each project). Issue #2216: Pages still passed the
15 minutes of its job.

## Why

After AD-1350 the Pages job needed 772 s for the step "Build the report of each fixture" (the last
runs before: 799 s, cancelled). Only the system run still ran twice, once for the JSON report and once
for the page, because its page frame holds the key `explain`, which the JSON report does not
(`native/core/src/system.rs`: `if topology || html`). Each system run scans the shell, `native/` with
compiler facts and the Studio UI.

Measured on the page form of the system run (main `a2d3bd86`): the frame without the key `explain`
equals the file of `--format json` byte for byte. Local gallery build with an empty facts directory:
system run 140 s with two runs, 61 s with one.

## Decision

`report_gallery._reports` takes `page_only`, the keys that only the page needs. The system run names
`explain`. They stay out of the JSON report and out of the row. No other run changes.

## Checks

`tests/test_report_gallery.py` (`explain` stays out of the JSON report and the row).

## Not done yet

The core part and the system run both scan `native/`. Sharing one scan between a part page and the
system page needs a change of the core.
