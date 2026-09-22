# AD-90 Decision-relevant evidence is never neutral metadata

## Decision

Archkeel claims only what deterministic evidence proves. A position it sees without enough
evidence, or with more than one possible origin, stays `UNKNOWN`. Two paths to one proven origin
are not ambiguous.

`PASS` means no violation among decided positions. It does not mean full coverage. Decided and
UNKNOWN positions remain separate measurements.

Baseline `roles` stay outside fingerprint identity, but AD-85 uses them to decide which public
entry lost its last importer. They are therefore semantic evidence. `validate --against` reports
every role-only change, even when fingerprint and count are unchanged. Schema 1.1 records roles
from typed `source_module` and `target_module` facts and writes them sorted. The baseline parser
rejects every field outside fingerprint, count and roles; unclassified metadata cannot reach a
verdict.

## Why

Calling a field explanatory does not make it neutral when validation reads it. Silent role drift
could suppress a different `interface.unused` diagnostic while the baseline looked unchanged.

## Check

`tests/test_widening.py` pins role-only drift through the pure comparison and a real
`validate --against` run. `tests/test_baseline.py` rejects metadata outside the typed fields.
