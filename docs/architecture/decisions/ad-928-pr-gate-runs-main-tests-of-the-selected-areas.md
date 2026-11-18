# AD-928: The PR gate runs main tests of the selected areas

The PR gate runs the same Python test selection as main for a change under `native/` or
`src/archkeel/cli/`. Each such change selects every area. A native change also runs the Rust
workspace tests through the same target as `native-check`. Changes to the Makefile, area table or
PR workflow run the same tests. Other changes keep the PR selection.

The core connects the native crates, the CLI and the collectors. A path-to-one-area rule missed
the collector regression in #1880. The PR-only exclusions missed the report size test in #1860
and the CLI and core tests in #1866. The missing Rust report tests let #1869 pass before main failed.
The broad selection avoids a
second dependency table that can become stale.

We reject keeping the three-minute budget at the cost of these tests. On a local macOS host, the
warm Rust workspace tests took 109 seconds. A cold report-only test took 18 seconds. Selecting
all areas collects 5,571 main-tier Python tests instead of 2,391 PR-tier tests. These are local
measurements, not a hosted gate duration. The hosted job keeps its 15-minute timeout pending measurement.

The gate does not run nightly slow tests or wheel tests. Changes outside native and CLI still rely
on the existing path-to-area rules. The selected tests and the Rust workspace tests can expose
failures that were already on main. `tests/test_area_selection.py` and `tests/test_make_gate.py`
check the selection and the gate recipe.
