# AD-610: Check literal schema extensions

The Rust collector models the registry derives in AD-554 only after it proves their identity and
checks each helper attribute. The `schemars` helper accepts `extend` with expressions. Those
expressions can call code or expand macros that the collector cannot safely model.

The collector accepts `extend` only when each key is a string literal and each value is a Rust
literal. The existing registry and namespace proofs still apply. Expression values keep the gap.
Other attribute macros also keep their own gap.

We reject accepting every extension expression: it can hide a dependency. We reject changing the
report schema to avoid the helper: the collector can check the literal form for every project.
The Rust collector tests cover literal extensions, expressions, shadowed derive paths and foreign
attribute macros. The native self-check exercises the report schema.
