# AD-544 A Rust receiver type can follow workspace re-exports

**Status.** Proposed. Part of #880. Fixes part (a) of #1215.

The written type of a receiver can name an item in another workspace crate. The type resolver
follows explicit `use` and `pub use` leaves to one struct or enum. Each module on the path must
be present in every configuration. A conditional use, glob, macro that can add an item, duplicate
binding, alias, unplaced type or ambiguous crate keeps the type unknown. The resolver follows at
most eight re-exports. A caller with an unproved macro also keeps the type unknown. AD-556 gives
the rule for a direct path into a non-root module of another crate.

The receiver still needs every first-step proof of AD-524. The resolver does not infer the type
of a local value. The earlier intra-crate resolver also refuses a conditional `use` when it
places a type. A generic parameter that can hide the root of a path keeps the path gap.

The known type is not itself an edge. AD-524 records an edge only when it proves the one visible
inherent member and the receiver form. A path call `T::m` has its own proof: explicit paths give
the type, the type is exact, exactly one inherent member `m` of an exact block is read, the member
has only inert attributes and the caller can see it for certain. The path keeps its gap when a
block of an unplaced type, a macro or a trait of the workspace has a member `m`, when the type is
an enum with a variant `m`, when a name before `m` has generic arguments, and when a macro of the
file can give the first name of the path again: a macro in statement or item place that is no
silent macro of `std`, unless the path starts at `crate`, `self`, `super` or `::`. A member that
the caller cannot see for certain is a gap to its module, not an edge. A trait can provide
an associated function when no inherent function is available; an inherent function wins when
both are available. `rustc` checks both cases in the plants.

`native/rust/src/modules/state.rs` holds the index state and explicit cross-crate type lookup.
`scan_path_safety.rs` records conditional uses and names that generic parameters can hide. The
checked module state is separate from the resolver so the module graph has no cycle.

`tests/test_collector_false_pass_rust_path_receiver.py` checks the first-step receiver, the
conditional import, the generic shadow and the path call across crates.
`tests/test_collector_false_pass_rust_path_proof.py` checks the same-crate path call: the macro
forms, the enum variant, the member that the caller cannot see and the generic arguments. The
self-check pin changes only for measured rows.
