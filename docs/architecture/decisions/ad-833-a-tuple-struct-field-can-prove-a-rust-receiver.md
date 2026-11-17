# AD-833: A tuple struct field can prove a Rust receiver

Status: accepted. Extends AD-804. Part of #1571.

## Context
The collector kept a pair gap for `w.0.m()` even when the type of the receiver was written
in an exact tuple struct.

## Decision
Store a tuple struct field by position and resolve it with the same checks as a named
field. Keep the gap if a field attribute can change the field positions. A built-in tuple
projection, such as `pair.0`, still has no proof.

A position taken from the source alone is unsafe. A `cfg` can remove a field and shift a
later field to that position.

## Evidence
The tests in `test_collector_false_pass_rust_own_file_method.py` compile and run both forms
with rustc. The exact position gives FAIL for the forbidden call. The position that can
change gives UNKNOWN.

The native self-check keeps the same verdicts. The proof removes an inherent `push` gap
from TypeScript collector `definitions` to `scope`. An independent trait gap remains for
that pair.
