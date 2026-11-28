# AD-1350: The compiler facts work is cached and the gallery scans once

Status: accepted. Issue #2216 (main CI and Pages cancelled by the 15-minute job timeout).

## Why

The self-check reads `native/` with compiler facts. The core builds the workspace with the compiler
driver in `~/.cache/archkeel/rustc-facts`. CI and Pages did not cache that directory, so each run
built the driver and checked the workspace from nothing.

Measured on `main` (2026-11-27), step "Check native/ and the Python shell with the core":

| Runs | Build the core | Self-check step |
|---|---|---|
| 22 green runs | 79-84 s | 478-630 s |
| 9 runs cancelled at 15:15 | 103-106 s | 742-782 s |

The step is 40 % slower on the slow runners, and the job has 15 minutes. The native scan alone took
385 s (green) and 568 s (cancelled); the phases of the core explain 78 s of it. The rest is the
workspace build.

Local measurement, same scan (`archkeel report --config native/archkeel.toml --topology`):

| Facts work | Time |
|---|---|
| empty (what CI does) | 177 s |
| kept, sources touched as after a checkout | 119 s |
| kept, sources unchanged | 73 s |

The three results are byte-identical.

The Pages job `make report-gallery` took 669 s, 726 s and 746 s in its last three green runs and then
passed 15 minutes. Locally one build takes 490 s, of which the self runs are 400 s and the 36 fixture
projects 3 s. Each project ran the core twice: once for the JSON report and once for the page.

## Decision

1. CI saves the facts work under a key that holds the hash of the native tree. A push that leaves
   `native/` alone finds the exact key and saves nothing. A push that changes it restores the latest
   entry and builds only what changed. Pages restores the latest entry and never saves.
2. The gallery runs the core once for each project. The page form with `--json` writes the page and
   prints the envelope. The JSON report is `envelope.frame` serialised without spaces; this equals
   the file of `--format json` byte for byte. The system run keeps two runs, because its page form
   adds `explain` rows to the frame.

No timeout changes.

## Checks

Local gallery build, all 86 published files, before and after: identical, except the Explorer
report, which differs between two runs of the old code too (a scan of `.` sees the output of the
gallery). `tests/test_report_gallery.py` checks that the JSON report is the frame of the one run.

## Not done yet

The lint job still scans `native/` and the shell again inside `make self-validate-system`. That scan
costs 112-166 s on CI. Removing it needs the system run to give the verdicts of the parts, which is a
change of the gate (AD-1260), not of the cache.
