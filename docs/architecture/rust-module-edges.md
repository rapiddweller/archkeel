# Rust module edges (AD-335, slice 5b-2c)

Amendment of [AD-335](decisions/ad-335-archkeel-checks-the-rust-of-native-with-its-own-contract.md).

- The collector writes the edges between the modules of one crate with the record kinds `import`
  and `reexport` (`pub use`) of `archkeel-facts`: no new kind. A path that starts at `crate`,
  `self` (level 1) or `super` (level n + 1), a child `mod`, a `use` binding or a glob `use` is
  resolved against the module index of the walk. The rule of 5b-1 holds: a name that the file
  declares more than once and that may name a module is UNKNOWN. An inline `mod` folds into its
  file. A binary names the library of its package by the package name. A path into another crate of
  the workspace names its deepest module.
- A glob is followed into the module that it names, with the names that module binds. A glob that
  the scan cannot follow, a `use` path that starts with a name that a glob may bring in, a `super`
  above the root, two `macro_rules!` of one name and a relative path in a `macro_rules!` body are
  UNKNOWN. A `crate::` path in a macro body is an `import` edge of each call and a `macro_body` edge of the file
  that holds it (AD-349); no cycle or layer rule reads `macro_body`. A call of a macro of the crate is
  an edge to the module that defines it. A call that the scan cannot place is UNKNOWN.
- `crate_edges_only` is false for the Rust profile, so a rule or a component below a crate root is
  decided from the edges. A rule kind that nobody reviewed stays UNKNOWN. `interface_boundary`
  stays unsupported until the uses of an item are resolved (5b-4b). The definitions are read since
  5b-4a ([AD-351](decisions/ad-351-the-rust-collector-reports-definitions-and-never-invents-one.md)).
- A re-exporting module is the dependency: `a` uses `b` through `pub use crate::b::make;` in `c`
  as `a -> c`, and `c -> b` is a `reexport` record. A rule on a module pair reads direct imports
  ("`a` must not import `b` directly"); a cycle or a layer rule reads both edges
  ([AD-356](decisions/ad-356-a-method-of-another-module-is-an-edge-or-a-pair-gap-in-rust.md)). The
  same for a glob re-export.
- A method of an `impl` block in another module than its type is an edge when a path names it, and
  a pair gap `a -> b` when a method call may reach it or a glob brings in a trait of `b` whose
  method `a` may call. The host drops the pair gap when the contract lets `a` use `b` and the edge
  closes no cycle (AD-356).
- Edition 2015 (or no edition in the manifest, also `edition.workspace` without a workspace
  value): a `use` path and a `::` path start at the crate root, so a first name that is a module of
  the root is that module.
- Oracle: delete `mod m;` from a copy of `native/` and run `cargo check --all-features`: the files of
  the crate with a name resolution error (`E0432`, `E0433`, `E0412`, `E0425`, `E0405`, `E0422`,
  `E0423`, `E0531`, `E0599`) are the files with an edge into `m` or below it. `make native-check`
  runs seven modules (`tests/test_collector_native_rust_module_oracle.py`). A one-off run over all
  108 modules of `native/` had no missed edge, except where `rustc` blames a macro definition for
  the error of a call; it is not part of the gate. A file with `E0599` for a method of an `impl`
  in `m` has an edge into `m` or a pair gap to it (AD-356). Not seen, and PASS is possible: an item
  that a macro generates, and a trait `impl` in another module than its trait and its type
  (`docs/known-limits.md`).
