# AD-360 A second engine is compared with recorded oracles per section and rule family

**Status.** Accepted. Epic #880, WP6 slice 0a (the dual-run harness).

**Decision.**
1. `make dual-run-record` runs the Python engine on each case of the corpus and writes one oracle
   per case to `tests/dual_run/`. The corpus is each fixture with an `archkeel.toml`, each report
   variant of the demo catalog and each golden case root that is not a fixture (344 cases).
2. An oracle holds the case (fixture, configuration, baseline and overlay files), so it runs
   without the catalog code. It holds L1, the verdict map (rule id to kind and status), and L2,
   the canonical rows of each section in `SECTIONS` of `tools/dual_run_oracle.py`. A canonical
   row is the JSON text with sorted keys and the strings of the string table expanded.
3. A section of 4 KiB or less keeps its full rows. A larger section keeps the id, a digest and
   the rule ids of each row. A demo variant keeps only the rows that differ from its fixture,
   and the digest of the fixture section, so a stale delta fails.
4. `make dual-run` runs a candidate engine and compares it with the oracles. The order of the
   rows is part of L2. A difference names the case, the section or `rules`, the row id and the
   first differing row: dropped, added, moved, or the first differing field.
5. A slice compares only what it owns: `--sections` and `--families` (a family of WP6-0 or a rule
   kind). The rows of `violations` and `unknowns` belong to the family of their `rule_ids`.
6. L3 (binding ids and digests) is compared where it is part of a row. A family that changes to
   digest v2 records its oracles again with its own decision record.
7. A second engine is a command (`--engine-command`). It reads one JSON request on standard input
   and writes one engine frame on standard output. Request: `protocol`
   (`archkeel-dual-run-1`), `case`, `root`, `config`, `baseline`, `contracts` (path to text),
   `reply` (`null` until the core ingests a collector reply), `sections`. Frame: `rules` (id to
   `[kind, status]`) and `architecture` (columnar `architecture.json`) or `sections` (name to
   canonical rows). `python -m tools.dual_run serve-python` serves the Python engine this way.
8. `--bench NAME=PATH[:CONFIG]` adds a local project. Its oracle goes to `test-artifacts/`, and the
   run prints only its counts.
9. The harness commits each case with a fixed date. Then the commit, and each binding to the
   source identity, is the same in each run.

**Reason.** The Rust model and evaluator replace `ir/` and `check/` one family at a time. Each
slice needs a proof that it gives the same verdicts and rows as Python. The proof must stay after
the Python code is deleted, so the oracle is recorded data and not a second live run.

**Rejected.**
- A hash of the whole `architecture.json`. A mismatch then shows no section and no row.
- Oracles without the delta form. The demo variants alone would need about 5.4 MB; the whole
  corpus with the delta form needs 2.7 MB.
- Tests that import evaluator internals as the oracle. They go with the code that they test.
- One oracle file for the whole corpus. Two slices that record again would always conflict.

**Limit.** The run takes about 36 s on 18 cores and 323 s of CPU time, so about 50 s on 8 cores. A change of a
fixture changes the deltas of its variants: record the fixture and its variants together. The
request carries no collector reply yet, so a candidate reads the sources below `root`.

**Tests.** `tests/test_dual_run.py`: `test_the_python_engine_equals_its_oracle`,
`test_a_changed_verdict_names_the_rule`, `test_a_dropped_row_names_the_section_and_the_id`,
`test_a_reordered_row_is_a_difference`, `test_a_changed_field_of_a_full_row_names_the_field`,
`test_an_added_last_row_is_a_difference`, `test_a_slice_compares_only_what_it_owns`,
`test_a_family_owns_the_rule_rows_of_its_rules`, `test_a_delta_oracle_reads_back_its_rows`,
`test_each_corpus_case_has_one_oracle`, `test_a_command_engine_with_a_planted_difference_fails_the_run`.
