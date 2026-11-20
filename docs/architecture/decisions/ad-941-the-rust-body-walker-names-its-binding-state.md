# AD-941 The Rust body walker names its binding state

**Decision.** Let the receiver scan start the body walker after it reads the
bindings. The walker holds a mutable reference to `Params`. `Params` does not
start the body walker.

**Reason.** `Params` was the only implementation of `Binder`. Naming it
exposed a cycle: `scan_params` built the walker and the walker called back into
`Params`. Move the order of the scan steps to the receiver scan. Keep the
checks for attributes and nested macros before the walker starts.

**Rejected.** Put the return call behind `dyn Binder` again. This would hide
the same dependency, not remove it.

**Limit.** The collector still reports a possible return edge because of the
`Visit` implementation. The module rule is UNKNOWN, not PASS. Both modules
remain in `rs-text`. The component rule still passes.

**Tests.** The native self-test checks all three module pairs. A temporary
copy routes the body walk through `params` again and must report both
observed edges of the cycle. The Rust collector tests cover the bindings.
