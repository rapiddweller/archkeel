# AD-360 A second engine is compared with recorded oracles per section and rule family

**Status.** Accepted. Epic #880, WP6 slice 0a (the dual-run harness).

**Decision.**
1. `make dual-run-record REASON=...` runs the Python engine on each corpus case and writes one
   oracle per case to `tests/dual_run/`. It refuses uncommitted sources, prints each difference
   that it overwrites and logs the reason in `RECORDINGS.md`. The corpus is the fixtures, the
   report variants of the demo catalog, the golden case roots, and `tests/dual_run/cases.json`:
   the false-PASS probes (`python -m tools.dual_run_capture` writes them) and `native/` at a
   pinned commit. A Rust case runs the Rust collector of the workspace, pinned.
2. An oracle holds its case, so it runs without the code that made it. It holds L1, the verdict
   map (rule id to kind and status), and L2, the canonical rows of each section that
   `tools/dual_run_schema.json` lists. A canonical row is JSON with sorted keys and expanded strings.
3. A section of 4 KiB or less keeps its full rows. A larger section keeps the id, a digest, the
   rule ids and the key fields (`kind`, `title`, `subjects`, `file`, `line`) of each row. A demo
   variant keeps only the rows that differ from its fixture.
4. `make dual-run` (Full) compares a candidate engine with the oracles. The row order is part of
   L2. A difference names the case, the section or `rules`, the row id and the first differing row
   with its expected content. A section outside the schema, a failed engine and an engine timeout
   are differences.
5. A slice compares only what it owns: `--sections` and `--families` (a family of the schema or a
   rule kind). An unknown name, a case glob that selects nothing, 0 projects, and 0 owned rules
   are errors. A `violations` or `unknowns` row belongs to the family of its `rule_ids`; a row
   without rule ids belongs to every family.
6. L3 (binding ids and digests) is compared where it is part of a row. A family that changes to
   digest v2 records its oracles again under its own decision record.
7. A second engine is a command. It reads a JSON request on standard input (`protocol`, `case`,
   `root`, `config`, `baseline`, `contracts`, `collector_argv`, `pinned`, `reply`, `sections`) and
   writes a frame: `rules` and a columnar `architecture` or the canonical `sections`.
   `python -m tools.dual_run serve-python` serves the Python engine this way.
8. The harness commits each case with a fixed date, so a binding to the source identity is stable.
9. The Python adapter pins the Archkeel version that the engine sees to `0.0.0`: the host expects
   it, and the reply of a collector of this install carries it. A member inventory binding reads
   that version, so the oracles hold for an install from Git too (`tools/dual_run_python.py`).
10. A rule kind with fewer than `fail_case_minimum` FAIL cases of its own (distinct violation rows)
   is in `fail_case_gap`. The slice of that kind adds FAIL cases before it deletes Python code.

**Amendment (2026-11-11, AD-372).** The request of point 7 is `archkeel-dual-run-2`: it also
carries `namespace` and `standard_library`, which the shell reads, so the core reads no file.

**Amendment (2026-11-12, AD-379).** The request is `archkeel-dual-run-3`: it also carries
`insides`, the inside contracts that the shell read for the paths that the last frame named.

**Reason.** The Rust model and evaluator replace `ir/` and `check/` one family at a time. Each
slice needs a proof that it gives the verdicts and rows of Python, and the proof must stay after
the Python code is deleted. A typo or a filter must never turn the proof into an empty PASS.

**Rejected.**
- A hash of the whole `architecture.json`. A mismatch then shows no section and no row.
- Full rows for every section: 7.0 MB of oracles; the key fields need 3.3 MB, the digest alone 2.7 MB.
- Tests that import evaluator internals as the oracle. They go with the code that they test.

**Limit.** 530 cases take 55 s on 18 cores. The probes with a tampered reply run the Python
collectors, so they test the evaluator on bad input only while those collectors exist. A Rust
collector change changes the Rust oracles: record them again in the same PR.

**Tests.** `tests/test_dual_run.py` (26 tests, in the PR suite): planted verdict, dropped, reordered
and added rows, unknown sections and families, rows without rule ids in a family slice, a run
that selects nothing, `record` guards, an engine timeout, the schema, the named gap, the fixture
subset equal to its oracles, also under another installed version.
