# AD-1224: The impl oracle has its own Full area

Status: accepted. Part of #2148.

## Why

The Full job `native collector evidence` took 25 to 37 minutes against the 15-minute budget. Its JUnit
file (run 45910338002) shows 46.5 summed minutes, of which `test_collector_native_rust_impl_oracle.py`
is 20.6. The other files are 5.5 minutes or less each.

## Decision

The oracle file forms the area `native impl oracle` with its own job and its own core cache steps. The
PR tier needs one light test in each area, so `test_collector_native_python_first_difference.py` (3
tests) moves with it. The area `native collector evidence` keeps the other Rust collector files. No test
is dropped, no tier changes, no timeout changes.

## Limit

The oracle file shares a module fixture, so each xdist worker keeps all of its tests together on one
worker (`conftest.py`). The area job is therefore as long as the file: the split alone does not bring
it under 15 minutes. Running the oracle on four workers is a separate change.

## Checks

`tests/test_area_selection.py`, `tests/test_core_cache.py` and the Full matrix test in
`tests/test_make_gate.py`.
