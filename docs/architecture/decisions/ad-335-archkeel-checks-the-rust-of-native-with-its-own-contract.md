# AD-335 Archkeel checks the Rust of native with its own contract

**Decision.** Archkeel reads Rust source with a native collector. It checks the workspace in
`native/` with this collector and the contract in `native/architecture-contract.json`. This is
slice 5b-1 of epic #880. Slices 5b-2 (module edges) and 5b-3 (cycles) amend this record.

1. `Language.RUST` has the profile `archkeel-rust-imports` and the file suffix `.rs`. The
   collector is the binary `archkeel-rust-collector` (crate `native/rust`, parser `syn`). Its
   request has the resolver `{"language": "rust"}` and protocol 8. `[scan] language = "rust"`.
2. A module is a file of the `mod` tree: `<namespace>.<crate>.<mod path>`. The host requires the
   namespace as the prefix of each module. The collector walks the tree from the target files of
   each `Cargo.toml` (`lib`, `bin`, `build`, `tests`, `examples`, `benches`) and follows `mod x;`
   and a literal `#[path]`. A file that no tree reaches is UNKNOWN.
3. An import record is one distinct path of a file whose first segment names another crate. A
   crate of the scan is a local target (the root module of that crate). Another dependency is an
   external target. `std`, `core` and `alloc` are builtin. A path inside one crate gives no
   record: module edges come with 5b-2.
4. A first segment is a crate when it is a dependency name in `Cargo.toml` (also `package =`
   renames, `workspace = true` and `[target.*]` tables) and the file declares no item of that name.
   The collector reads `Cargo.toml` with its own reader and starts no process.
5. A derive never makes a file UNKNOWN. A path inside an attribute is an edge, for example
   `#[serde(with = "crate_a::codec")]`. UNKNOWN, each with its reason: a macro call whose body has
   a path (the macros of `std` and `json!` are read as expressions), `macro_rules!`, `include!`,
   a `cfg` or `cfg_attr` on a `mod` or `use`, a `path` attribute that is not a literal, an attribute
   macro on a module, a missing or ambiguous module file, a syntax error, a file that two modules
   load, an unreadable `Cargo.toml` and a `[lib] name` that differs from the package name.
6. A `cfg(test)` and a `cfg(feature = "x")` of a feature that the manifest declares are read as
   true, so the edges are the union over all features. `native/typescript` has one such `mod`
   (`dump`). Any other `cfg` on a `mod` or `use` is UNKNOWN.
7. The profile copies the unsupported rules of TypeScript. A rule that needs a symbol, a call, a
   type or a construct says that the profile does not support it, and is never PASS.
   `interface_boundary` stays decided from the import records.
8. The host uses the bundled binary as the default collector (`archkeel/_native`, found with
   `importlib.resources`). Without it (sdist, unsupported platform) `Language.RUST` reports
   `missing_tool`. A configured `collector_argv` wins. `native/hatch_build.py` bundles a third
   binary with its own SBOM, and the six wheel jobs build it. Customers get the collector when
   platform wheels are published: `PUBLISH_NATIVE_WHEELS` of AD-317 is unchanged.
9. The contract of `native/` has the components wire, build, typescript and rust, `complete_assignment`,
   `complete_requires`, `no_component_cycles` and the use of `tree_sitter*` and `syn`. `make
   self-validate-native` runs it, and `make native-check` runs that target.
10. `cargo deny` `wrappers` checks the dependencies that `Cargo.toml` declares. The contract checks the
    paths that source uses. These are two facts, so both stay. A declared and unused dependency
    is a gap between them: the oracle found `sha2` in `archkeel-typescript-collector`, now removed.
11. `archkeel-build-support` holds the `build.rs` digest, so each collector has a build script of
    three lines and the digest has one owner.

**Reason.** The product must check its own Rust (dogfooding), and layering must have one owner:
the contract. The pytest and `layers.toml` stay until 5b-3, as `tests/test_collector_native_rust_oracle.py`
shows that both give the same crate edges.

**Rejected.**
- `tree-sitter-rust`: another C build and another `wrappers` entry. `syn` adds no crate to `Cargo.lock`.
- rust-analyzer: hundreds of crates and an API that changes.
- `cargo metadata` at run time: a child process and the network. It is the oracle in the tests.
- UNKNOWN for each feature `cfg`: it would make `native/` UNKNOWN for one `mod`.

**Limit.** Crate edges only. The module name holds the whole path, so a chain of n nested modules
writes bytes in proportion to n squared. A reply of a file with many paths takes about 20 KB of memory
for each path. The scan does not expand macros, does not read `build.rs` output and does not
know the active features. `init` and `explore` do not support Rust yet.

**Check.** `cargo test` (reader, scan, tree, facts), `tests/test_collector_native_rust.py` (each
reason, FAIL for a bad edge, a rename, a missing component and a cycle),
`tests/test_collector_native_rust_oracle.py` (`cargo metadata`, the layer test, same bytes twice),
`tests/test_collector_native_rust_scaling.py` (six shapes: time at most 3, memory at most 2.5),
`tests/test_collector_native_rust_language.py` and the wheel test (the installed binary replies).
