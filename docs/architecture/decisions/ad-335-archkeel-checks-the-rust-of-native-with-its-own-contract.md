# AD-335 Archkeel checks the Rust of native with its own contract

**Decision.** Archkeel reads Rust source with a native collector. It checks the workspace in
`native/` with this collector and the contract in `native/architecture-contract.json`. This is
slice 5b-1 of epic #880. Slices 5b-2 (module edges) and 5b-3 (cycles) amend this record.

1. `Language.RUST` has the profile `archkeel-rust-imports` and the suffix `.rs`. The collector is
   the binary `archkeel-rust-collector` (crate `native/rust`, parser `syn`). Its request has the
   resolver `{"language": "rust"}` and protocol 8. `[scan] language = "rust"`.
2. A module is a file of the `mod` tree: `<namespace>.<crate>.<mod path>`. The walk starts at the
   target files of each `Cargo.toml` (`lib`, `bin`, `build`, `tests`, `examples`, `benches`) and
   follows `mod x;` and a literal `#[path]`. A file that no tree reaches is UNKNOWN. A module
   deeper than 64 levels is UNKNOWN: its name holds the whole path, so memory grows with the square
   of the depth (the deepest module of the `uv` corpus has depth 4).
3. An import record is one distinct path of a file whose first segment names another crate. A crate
   of the scan is a local target (its root module). Another dependency is an external target.
   `std`, `core` and `alloc` are builtin. A path inside one crate gives no record (5b-2).
4. A first segment is a crate when it is a dependency name in `Cargo.toml` (`package =` renames,
   `workspace = true` and `[target.*]` tables too) and the file declares no type, module or `use`
   rename of that name. A path that starts with `::` names a crate, and no local name hides it. A function, a constant and a static are values, so they do not hide a
   crate. The collector reads `Cargo.toml` itself and starts no process.
5. A derive never makes a file UNKNOWN. A path in an attribute is an edge, also in a string under
   a key that holds paths (serde `with`, `bound`, `remote`, ...), read as tokens; a text with `::`
   that does not read is UNKNOWN. A message or a name (`deprecated(note = ...)`) and a lint list are no path. UNKNOWN, each with its reason: a macro call with a path in its body
   (the macros of `std` and `json!` are read), `macro_rules!`, `include!`, a `cfg` or `cfg_attr` on a
   `mod` or `use`, a non-literal `path`, an attribute macro on a module, a missing or ambiguous
   module file, a syntax error, brackets nested deeper than 256, a file that two modules load, an
   unreadable `Cargo.toml` and a `[lib] name` that differs from the package name.
6. `cfg(test)` and `cfg(feature = "x")` of a declared feature are read as true, so the edges are the
   union over all features. Test code is production code here: `cfg(test)` modules, the `tests/`
   targets and the dev- and build-dependencies give edges like any other. Slice 5b-2 marks the scope.
7. The profile copies the unsupported rules of TypeScript and adds `interface_boundary`: every
   target of a local crate is its root module, so a public list that names the root would pass.
   `crate_scope.py` makes each scope that needs the edges inside a crate UNKNOWN until 5b-2:
   a component, and each field that names a module in `forbidden_dependency`,
   `allowed_dependency` and `sibling_isolation` (`members` too), when the name is below a crate
   root or covers the modules of one crate; a module-level cycle rule. The same check runs on the
   contract of a component (`inside`). A table over the whole catalog lists each rule kind and
   field, so a new kind or field fails a test until a person reviews it. A profile must declare
   `crate_edges_only`, with no default.
8. The host uses the bundled binary as the default collector (`archkeel/_native`, found from
   `__file__` in `cli/observe.py`). Without it `Language.RUST` reports `missing_tool` with the path.
   A configured `collector_argv` wins. `native/hatch_build.py` bundles a third binary with its SBOM.
   Customers get the collector when platform wheels are published (`PUBLISH_NATIVE_WHEELS`, AD-317).
9. The scan runs in a thread with a stack of 256 MiB, and a file with brackets nested deeper than
   256 is UNKNOWN, so no file ends the whole scan. A path that leaves the snapshot, by name or by a
   link in the middle of it, is never read (the rule of the TypeScript snapshot).
10. The contract of `native/` has the components wire, build, typescript and rust, the rules
    `complete_assignment`, `complete_requires`, `no_component_cycles`, and the use of `tree_sitter*`
    and `syn`. `make self-validate-native` runs it, and `make native-check` runs that target.
    `cargo deny` `wrappers` checks the declared dependencies, the contract the used paths: two
    facts, so both stay. The oracle found `sha2` declared and unused in the TypeScript crate.
11. `archkeel-build-support` holds the `build.rs` digest for both collectors.

**Reason.** The product must check its own Rust, and layering must have one owner: the contract.
The pytest and `layers.toml` stay until 5b-3, as the oracle test shows the same crate edges.

**Rejected.** `tree-sitter-rust` (another C build). rust-analyzer (hundreds of crates).
`cargo metadata` at run time (a child process; it is the oracle). UNKNOWN for each feature `cfg`.

**Limit.** Crate edges only. About 25 KB of memory for each import (uv: 15,536 imports, 370 MiB).
The scan does not expand macros or read `build.rs` output. `init` and `explore` do not support
Rust. `syn` brings `unicode-ident`: `deny.toml` has one licence exception (Unicode-3.0).

**Check.** `cargo test`; `tests/test_collector_native_rust.py` (each reason, each false PASS above);
`..._oracle.py` (`cargo metadata`, the layer test, same bytes); `..._scaling.py` (seven shapes);
`..._language.py`; the wheel test.
