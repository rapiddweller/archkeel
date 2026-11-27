# AD-1262: The impl oracle keeps no list of files that reach an impl only over a path

Status: accepted. Part of the drift-gates audit of 2026-11-27 (family C). Amends #2108.

## Why

The nightly impl oracle (#2108) deletes the impl blocks of each file of `native/` and checks the files
that then fail to compile. Two assertions followed. The first: each failing file must be reached by the
collector over its held pairs (a missed edge is a candidate for a false PASS). The second: the files
that have no direct pair into the impl file must equal a list, `DIRECT_ONLY`, measured on one checkout.

The second list is an observation of this tree. #2124 failed on it because the compiler stopped early
(fixed in #2145, `--keep-going`). A new file that reaches an impl over a re-exporting module changes the
list although nothing is wrong.

## Decision

`DIRECT_ONLY`, the `Held.holds` method and the equality assertion are deleted. The first assertion stays:
the oracle still fails when the compiler runs code of an impl in a file that the collector does not
reach (the real soundness check; it was the one that found the missed edges of #1005).

## The truth the list asserted, and where it is tested

Truth: a file that reaches an impl only over a re-exporting module has no direct pair, so a direct
`forbidden_dependency` rule is PASS by design (AD-772) and `indirect: true` is FAIL (AD-1085).
Now: `tests/test_collector_rust_facade_reexport.py` runs that case on a controlled Cargo workspace with
the compiler as witness (a counter that prints 101), for item, function, glob and method forms.

## Checks

`tests/test_collector_native_rust_impl_oracle.py` (live oracle, nightly),
`tests/test_collector_rust_facade_reexport.py`.
