# AD-89 Selected measurements share the validation baseline

A contract may select `cycle_edges`, `private_crossings`, `typing_positions`,
`calls_unresolved` and `untyped_private_accesses` under
`declarations.measurement_budgets`. Each entry cites its provenance. Baseline schema 1.2 stores
the accepted value beside known violations.

The value must match the complete observation. A rise fails and refuses `--write-baseline`
unless `--accept-new` is explicit. A fall also fails until `--write-baseline` records it. Under
`--against`, raising or dropping an accepted value and removing a budget declaration are
widenings. Adding a declaration is a narrowing.

Reason: these scalars already come from `measure_python_ratchets`. Reusing that profile and the
existing baseline gives one comparison and one write path. Component size, construct counts and
facade measurements stay report-only because they are not in that validated profile. Archkeel
does not turn missing measurement evidence into PASS; an incomplete observation exits 2.

Check: `tests/test_measurement_budgets.py` covers pass, rise, fall, invalid input and widening.
The shop catalog runs clean and rising `cycle_edges` variants. Archkeel selects all five values
in its own contract and `make self-validate` checks `architecture-baseline.json`.
