# AD-465 A scan does not depend on build output that another process changes

**Status.** Proposed. Part of #880. It extends AD-432 and AD-420.

**Decision.**
1. The search for a Cargo config (`registry::overrides` in `archkeel-rust-collector`) does not enter a
   build directory. A directory is build output when it holds a regular file `CACHEDIR.TAG` or
   `.rustc_info.json`. The walk of the collector already skips such a directory (`source.rs`).
   The config files of the build directory itself still count.
2. The survey of the work budget (`survey_within` in `archkeel-collect`) does not refuse a scan when
   a directory below a proven cache cannot be listed or an entry of it cannot be read. It skips that
   directory. The same failure outside a proven cache stays a refusal.
3. A test that reads this checkout scans a frozen copy of `native/` (`tests/frozen_native.py`).
   A test that runs `cargo` in the shared `native/target` holds the build lock of all workers.

**Reason.** `cargo` and `rustc` add and remove temporary directories in `native/target` while the
tests run on parallel workers. A scan that lists such a directory gets an unreadable directory
(a gap, UNKNOWN) or the refusal `cannot list` (exit 2). The gate of other authors was red once and
green on the rerun. The tag already marks the directory as build output, so its content decides nothing.

**Rejected.** Retry of the scan in the test: it hides the defect. A gap for the vanished directory
only in tests: production code differs from the tested code. A check of the tag signature in the
collector: the snapshot would record the tag as an input and change the input digest.

**Limits.** A false tag in a source directory hides a Cargo config below it from the search. The
walk of the collector hides the source files of that directory in the same way, and the tag needs a
regular file. The survey still lists a proven cache, to charge its entries to the budget of their own.
A test that scans a copy does not see a change that is not yet in the working tree.

**Tests.** `native/rust/src/registry_tests.rs` (a config below build output, a locked directory
inside and outside build output). `native/collect/src/repository_tests.rs`
(`a_directory_that_cannot_be_listed_below_a_proven_cache_is_no_refusal`).
`tests/test_native_self_core_rows.py`, `tests/test_cli_native_core_scan_rust.py`,
`tests/test_cli_report_output.py` and `tests/test_collector_native_rust_oracle.py` read the frozen copy.
