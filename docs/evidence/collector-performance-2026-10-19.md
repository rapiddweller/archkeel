# Performance checkpoint, 2026-10-19

LOCAL VERIFIED: one sequential Main/candidate pair, Python 3.11.12. Main source:
`680541d93b3de3a1cf54e101f1021190b03a5432`. Candidate source manifest:
`1791473d1cb93f6f0e40a78c4a84fc778a5aba8410520b33522902096fe27af7`.

The actual CLI includes survey, provider-bound collection, strict process-boundary
validation, Core evaluation, projection, canonical JSON, HTML, files and shutdown.
Inputs: 1,174 EE files and 37 contracts at
`fae223beab602bc66d7c3cf98a19df30bafbe224`; 300-second collector deadline and
256 MiB output limit unchanged. Both processes loaded verified frozen Python sources.
Installed distribution metadata was shared and does not identify either source revision.

| Whole CLI | Main | Candidate |
| --- | ---: | ---: |
| Wall time | 116.50 s | 84.67 s |
| CPU time, OS child accounting | 116.10 s | 84.08 s |
| OS RSS high-water mark | 2.141 GB | 2.141 GB |

Wall time fell 27.33%; CPU fell 27.58%. RSS is not aggregate process-tree memory.
The baseline had 99 bytecode caches, all verified against fresh compilation of its
frozen sources; the candidate had none. This startup asymmetry favors the baseline.
Host timing varied between experiments; compare within this pair only.

Both exits were zero. Reports matched completely after normalizing only the analyzer
code digest; CLI JSON matched after normalizing only the output directory.
Both HTML files matched raw bytes. Coverage, 397 PASS/34 UNKNOWN assessments,
184 UNKNOWN positions and zero violations were identical. Each run emitted three
artifacts totaling 111,232,211 bytes. Private paired receipt SHA-256:
`dd6205f4e09068997404172544f987a2513c99658302b1d9d2fc289762a939ac`.

The changes remove repeated graph closure, namespace fanout, AST walks, JSON copying,
re-export scans, ownership decisions and coverage scans. Caches remain local to their
immutable snapshot; mutable binding and escape decisions remain live.
When producer JSON and semantic claims are both invalid, JSON validation now rejects
first. Regression tests cover that diagnostic-priority change.

A separate 25-module Cython prototype reduced compute-only wall time by 21.46% with
equal results. It is excluded from this package: native artifact provenance and
supported wheel builds remain unverified. GC suppression increased memory and was
also excluded. Neither experiment's gain is added to the whole-CLI measurement.

Local gates passed: native architecture validation, 437 collector-safety tests,
113 hygiene/Makefile tests, lint, typecheck, build and wheel/sdist smoke.

CI-ONLY VERIFICATION: pending. This checkpoint does not close the subsequent SPOT
and 500-line source/test/tool acceptance work.
