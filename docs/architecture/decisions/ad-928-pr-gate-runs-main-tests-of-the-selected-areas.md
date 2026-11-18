# AD-928: The PR gate runs main tests of the selected areas

The PR gate and main share parallel Python area jobs and a native check job. A change under
`native/` or `src/archkeel/cli/` selects the main-tier tests of its affected areas. A native
change also runs `native-check`. A report-only native change selects the CLI and report areas.
Other native and CLI changes select every area. Changes to the gate select every area and the
native check. Other changes keep the PR selection. Unselected jobs print `no matching paths`.

The core connects the native crates, the CLI and the collectors. A path-to-one-area rule missed
the collector regression in #1880. The PR-only exclusions missed the report size test in #1860
and the CLI and core tests in #1866. The missing Rust report tests let #1869 pass before main failed.
The native and CLI rules stay broad where the affected areas are not proven.

We reject keeping the three-minute budget at the cost of these tests. On a local macOS host, the
warm Rust workspace tests took 109 seconds. A cold report-only test took 18 seconds. Selecting
all areas collects 5,571 main-tier Python tests instead of 2,391 PR-tier tests. These are local
measurements, not a hosted gate duration. Hosted run 44318829263 passed the Rust tests in 4:48.
The serial Python tests reached 30 % in 9:05 before the 15-minute job timeout. Each parallel
PR job has a 15-minute hang guard. The shared main jobs retain their existing 30- and 40-minute
hang guards. The total hosted wall time remains to be measured.

The gate does not run nightly slow tests or wheel tests. Changes outside native and CLI still rely
on the existing path-to-area rules. The selected tests and the Rust workspace tests can expose
failures that were already on main. `tests/test_area_selection.py` and `tests/test_make_gate.py`
check the selection and the gate recipe.
