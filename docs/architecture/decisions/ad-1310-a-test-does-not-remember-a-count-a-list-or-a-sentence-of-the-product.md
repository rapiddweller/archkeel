# AD-1310: A test does not remember a count, a list or a sentence of the product

Status: accepted. Owner decision of 2026-11-27: purge every drift gate that is not ArchKeel itself.
Groups 6, 7, 9 and 10 of the sweep.

## Why

These checks failed after a legitimate change and caught no defect: a second inventory of the scaling
shapes, floors on the size of an oracle corpus, a persistent "known difference", lists of file names
and revisions that a snapshot keeps in two places, and copies of card text, issue numbers, section
order and fixture names. Each needed a hand edit at the next change. The truths that matter stay
tested: an oracle that is skipped or empty fails, a planted false PASS fails, a compiler comparison
fails when the collector gives a wrong edge.

## Decision and table

| Removed | Still covered by |
|---|---|
| `tests/scaling_coverage.py`, `scaling_script_shapes.SCRIPT_FIELD_COVERAGE`, and three tests of `test_collector_native_scaling.py` (shape inventory, kind classes, kinds of a shape) | the memory-bound tests on the nests that were quadratic (AD-323); none (owner decision) for the inventory |
| `found >= 30` skips in `test_oracle_guard.py` | the same test: the walk must find a skip and each skip names a tool |
| `len(PLANTS) >= 16` and the exact passing set in `test_cli_core_uml_nested.py` | each plant that the core passes must also pass in release 4.0.1 |
| `len(CASES) >= 30` and "a known miss must stay a miss" in `test_collector_native_rust_receivers_compiled.py` | a wrong edge fails for every case, known miss or not |
| `len(requests) > 50` in `test_cli_native_core_scan_rust.py` | the corpus must not be empty; "0 differences" is still required |
| `>= 230` common definitions and "the allowed difference is gone" in `test_collector_native_rust_definitions_oracle.py` | the oracle compares a non-empty set; the build script is the only allowed difference (a subset check) |
| attempt headings and counts 4/4/8/1 in `test_native_report.py` | each `compile_fail` fence names an error code, and `cargo test --doc` runs them |
| literal commits, file-name lists, suffix lists, exclusion lists in `test_project_demo_snapshots.py` | one identity check: each URL is `repository/blob/commit/path`; each hash equals the file; listed paths equal the files on disk |
| `test_report_gallery_cards.py` (premise text, card prose, issue numbers) | `test_report_gallery.py` escapes dynamic text; none (owner decision) for the prose |
| section order, navigation, intent-line prose, badge colour, gap-row text in `test_report_gallery.py` | the page builds, links exist, the intent and blocker fields are well formed |
| pin prose and the intent table of two real projects in `test_report_gallery_sources.py` | pin verification and copy tests |
| the fixture directory inventory and the `== 4` gap count in `test_cli_fixture_matrix.py` | the gap count equals the listed gaps; the intent test of the matrix (AD-1261) |
