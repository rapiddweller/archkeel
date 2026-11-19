# AD-941 The Rust body walker names its binding state

**Decision.** Let `Bodies` hold a mutable reference to `Params`. Remove `Binder`:
`Params` is its only implementation and the only binding state that the walker
receives.

**Reason.** `scan_params` constructs the walker. The walker already calls
`Params::typed` and `Params::bind_at` through dynamic dispatch. Naming the type
exposes both directions of this existing dependency without changing the calls.

**Rejected.** Treat an unresolved dispatch as proof of no cycle. The native
module rule must fail when both directions have evidence.

**Limit.** The native self-scan pins the one observed cycle until #1899 breaks
it. Both modules remain in `rs-text`. The component rule still passes.

**Tests.** The Rust collector tests cover the receiver bindings. The native
self-scan checks the rule status and the exact cycle in the pin.
