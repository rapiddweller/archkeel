# AD-1212: A drawn edge that only the compiler proves is a named hold when the scan has no facts

Status: accepted. Closes #2127. Amends AD-466 (`graph.drift`) and AD-1136.

## Why

`docs/architecture/native.md` draws the component edges that the compiler proves (AD-1136):
`core-baseline->report-payload`, `core-engine->model-terms`, `eval-rules->model-match`. A scan without
compiler facts cannot see them, so it reported `graph.drift`: "drawn and not found". The nightly test
`test_the_core_scans_its_own_workspace_with_no_shell_reply` scans a frozen copy without facts and failed.
The PR gate scans the live tree with facts on each PR and keeps catching stale edges.

Facts on in that test need nine cold `cargo check` runs (350 to 640 s of CPU) and do not fit the 600 s
of the core on a 4-core runner, with or without a cache (Full runs 45893796950, 45902694393, 45910338002).

## How the core knows (measured)

The diagram and the contract carry no evidence kind: a drawn edge is only a pair of labels. So the rule is:
no non-facts evidence **and** facts off **and** a possible compiler resolution.

1. Facts off: the reply has no type-reach fact (`Model::used_compiler_facts`), whatever the config says.
2. A possible compiler resolution: a kept or dropped pair gap with `execution` set (an impl may run) joins
   a module of each of the two components. This is the gap that a compiler `selected_impl` fact resolves.
3. The code shows no edge between the two components.

## Decision

A drawn edge that is not observed and meets 1 to 3 is the hold `graph.needs_facts`, one row for each edge:
"Drawn edge A -> B needs compiler facts". It is neither a `graph.drift` nor a confirmation. Both are
hygiene rows, so the run stays held (UNKNOWN, exit 3). A drawn edge with no such gap stays `graph.drift`.
An edge that a dropped gap already holds keeps its text of #1021. With facts on, nothing changes.

The nightly test asserts the exact set of these rows (`NATIVE_COMPILER_ONLY_EDGES`). A new stale edge fails
it as a drift; a new compiler-only edge in `native.md` is added to the set.

## Counter-examples

- A stale drawn edge with no code and no gap: still `graph.drift` (unit test; `drawn-not-found` in
  `test_cli_core_contract_hygiene.py`).
- An observed edge that is not drawn: still `graph.drift`.
- Facts on: the set of compiler-only edges is empty, so the gate behaves as before.
- Limit: a stale edge that has an unrelated executed-impl gap between its components is a named hold, not a
  drift, while facts are off. It is UNKNOWN, never PASS, and the gate (facts on) reports it as drift.

## Rejected

- Facts on, with or without a 2.5 GB cache or a larger runner: over the 600 s and the cache budget.
- A longer timeout: not a fix of the cause.
- Hiding the three edges from the copy of the diagram: duplicates the knowledge in the test.

## Checks

`native/core/src/hygiene_graph_tests.rs`, `native/core/src/hygiene_tests.rs`,
`tests/test_cli_native_core_scan_rust.py`, `tests/test_native_self_core_rows.py`.
