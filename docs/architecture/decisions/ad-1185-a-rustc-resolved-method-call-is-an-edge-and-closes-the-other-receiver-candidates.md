# AD-1185: A rustc-resolved method call is an edge and closes the other receiver candidates

Status: accepted. Amends AD-806, AD-900 and AD-1136. Step 3 of the trait-dispatch path (#2083).
This change can turn a held pair into PASS, and it exposes holds that a named gap masked.

## Why

The scan reads no types. A call `x.m()` whose receiver it cannot resolve gets a pair gap to each module that
has a member `m` in the file of a type (#1571). In the self-check, 875 of 1,202 `INTERFACE-BOUNDARY` holds were
such gaps (`as_str` 299, `is_empty` 92, `id` 81). The rustc driver already knows the callee of each call.

## Decision

1. **Driver.** One `call` record for each dot call that the compiler resolves to one function: the span of `m(..)`
   (`fn_span`) starts after the receiver, a path call is no dot call, and a call that a macro wrote is skipped.
   A trait method is resolved with `Instance::try_resolve` (concrete types only). A `dyn` call and a call
   with a type parameter give no record. The record holds the place, the callee, and for workspace code the
   module and the file of the callee. `PartialEq::eq` stays the operator site of AD-1136.
2. **Place.** The scan reads the method name (`node.method.span()`). Its line and column are the place
   of `m(..)`. A call in a macro argument keeps its own place. A hidden call from a macro body has the place of
   the macro and matches nothing.
3. **Decision.** A written candidate `(C, M)` at a place falls when every configuration holds the place with
   one and the same callee, and the file of that callee is not the file of `M`. The compiler proved another
   function, so the call cannot reach `M`. The file decides, not a module name: a name can map wrong (a binary target).
   The type arguments of the instance (Self included, opaque types revealed, closures and nested arguments) must not
   touch `M`: no argument is defined in the file of `M` or has an impl there (blanket impls always count), and none is
   open (a trait object, a function pointer, a coroutine, a parameter: only plain data and named types are known).
   The walk starts at the type arguments and at the types of the callee's inputs (the receiver of a method without
   generics is no argument). It enters the fields of every type, with associated types normalized, up to a budget of 300 types (more is open).
   A std type must also be a container, a smart pointer, a cell, a range or an iterator adapter; another one (`Waker` holds a vtable of
   functions) is open, so a callback that a field holds (a function pointer, a closure,
   a trait object) is seen. The rule is closed-world: what the walk cannot name keeps the candidate. A std adapter that runs a closure of `M` keeps the candidate. A foreign callee (`core`, `alloc`) falls the candidate too. An unresolved call (a trait object, a parameter) writes an open record of its place, so a test unit that
   dispatches differently vetoes. An unresolved call in the library and a
   configuration that lacks the place or changes the callee decide nothing. A test unit can only veto: a place that
   only test code holds decides nothing, and a test unit that names another callee keeps the candidate.
4. **Edge.** A callee in another scan module is a `selected_impl` edge (AD-1136) with the call as evidence,
   under the same file checks and the every-configuration rule. A candidate that the callee confirms stays a
   gap: the named use of `M` still needs its publication route.
5. **Named pairs.** The candidates that fell leave before the named pairs are read. A pair whose named
   candidates all fell keeps its execution candidates, and they are no longer read as named (AD-900).

## Effect on the self-check (local run, `ARCHKEEL_ALLOW_BUILD=1`)

- 39,655 resolved call places hold in all 9 configurations.
- `INTERFACE-BOUNDARY` holds: 1,210 before rule 5 (no change), 690 with it.
- `REQUIRES-COMPLETE`: PASS to UNKNOWN, 8,056 held pairs. They are execution doubts (a trait impl may run, AD-806)
  that a named candidate on the same pair masked. No violation, no FAIL.
- Pair gaps: 13,078 pairs as before. About 500 records changed their reason, because another candidate of the
  pair is now the first one.

## Counter-examples that were tried

Each is in `tests/test_cli_native_rust_resolved_call.py` with the real driver and a `cargo run` counter, or in
`native/rust/src/selected_edges_tests.rs`.
- A call through a local function value that `d::U` answers: `b` falls (PASS), `d` is an edge (FAIL).
- The same call that `b::S` answers: the counter shows `b` runs, `b` FAILs, `d` falls.
- A `dyn` call: no record, both gaps stay.
- A call that a feature changes: no callee holds in every configuration, both gaps stay.
- A call at another column, a test unit, a missing configuration, a changed callee: the gap stays.

## Not done yet

- A candidate that the callee confirms is still held for the interface; the route of the receiver type is not proven.
- A path call `T::m(..)` and a call that a macro wrote have no place that the scan reads.
- The `REQUIRES-COMPLETE` holds are the honest state. A later change can drop the allowed ones.
