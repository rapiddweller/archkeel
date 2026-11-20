# AD-1003 The shadowed module result needs no trait implementations

**Decision.** Remove `Clone`, `Debug` and `PartialEq` from the private `Shadowed` type.

**Reason.** The Python collector reads each result by reference. The tests compare its
fields and diagnostic text. No caller uses these trait implementations. The Rust
self-check records a possible runtime dependency on the module because it defines them.

**Rejected.** Exempt derived trait implementations from the check. A caller can still
run other derived trait implementations.

**Limit.** The Python diagnostic and dump format stay the same. Other sources of
unresolved Rust dispatch remain.

**Tests.** The Python collector's `names::tests` cover package shadowing and its diagnostic.
The native self-check measures the change in reported gaps.
