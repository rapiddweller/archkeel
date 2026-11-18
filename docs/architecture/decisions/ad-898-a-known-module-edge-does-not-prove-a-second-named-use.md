# AD-898: A known module edge does not prove a second named use

Status: proposed. Closes #1851. Part of #880.

## Context

An unresolved method call can reach a block whose module the caller already imports.
The pair deduplication keeps the known edge. The interface receipt then reads only
the first named use. A listed import can therefore turn UNKNOWN into a false PASS.

## Decision

- Keep the existing dependency pair. If it already has a known edge, write the
  unresolved named use as a source resolution gap in `unknowns`, not as a
  second coverage gap. Cite each call site, also when one glob can bind
  two calls on the same line.
- The store checks that the site names two distinct observed modules and cites the
  caller. The interface receipt reads the pairs with an unresolved crossing into
  a declared public surface. It still fails a proved unlisted use.
- `rust-item-routes-v2` is the live authority to judge the Rust interface. Both
  producer paths write the same site records. A v1 archive has no live authority.
  The store refuses a live v1 interface claim.

## Result

On the native self-check the fix adds 306 open interface pairs.
It leaves all 22,597 coverage gaps, other rule readings and statuses unchanged.

## Alternatives and limits

- A second coverage gap for a known edge changes what other rules know.
  Keep uncertainty about the name separate from uncertainty about the edge.
- A known import does not prove a different call, even if it names the same module.
  The fix does not teach the collector the type of the unresolved receiver.
- A separate process must preserve and validate both the capability and its site
  records before it can assert live interface support.

## Tests

`test_cli_native_rust_interface.py` compiles and checks the listed use,
the exact unlisted call, the unresolved call, and both orders of the mixed case.
It also checks two glob call positions on the same line and on separate lines.
`rust_tests.rs` checks canonical fact parity and refuses live v1 authority.
