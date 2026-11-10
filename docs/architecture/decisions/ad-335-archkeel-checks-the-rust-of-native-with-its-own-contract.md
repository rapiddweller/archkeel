# AD-335 Archkeel checks the Rust of native with its own contract

**Decision.** Archkeel reads Rust source with a native collector. It checks the workspace in
`native/` with this collector and the contract in `native/architecture-contract.json`. This is
slice 5b-1 of epic #880. Slices 5b-2 (module edges) and 5b-3 (cycles) amend this record.

1. `Language.RUST` has the profile `archkeel-rust-imports` and the suffix `.rs`. The collector is
   the binary `archkeel-rust-collector` (crate `native/rust`, parser `syn`). Its request has the
   resolver `{"language": "rust"}` and protocol 8. `[scan] language = "rust"`.
2. A module is a file of the `mod` tree: `<namespace>.<crate>.<mod path>`. The walk starts at the
   target files of each `Cargo.toml` and follows `mod x;` and a literal `#[path]`. A file that no
   tree reaches is UNKNOWN. A module deeper than 64 levels is UNKNOWN: its name holds the whole path.
3. An import record is one distinct path of a file whose first segment names another crate. A crate
   of the scan is a local target (its root module). Another dependency is an external target.
   `std`, `core` and `alloc` are builtin. A path inside one crate gives no record (5b-2).
4. One safe rule, with no model of Rust name resolution. A first segment that names a crate which the
   scanned crate reaches (a dependency of `Cargo.toml`, with renames, `workspace = true` and
   `[target.*]`, or `std`) is an edge. When the file also declares or imports that name anywhere
   (any item, `use` leaf or module, at any depth, in any namespace), the path is UNKNOWN ("A local
   name equals a crate name"). A path that starts with `::` is the crate; `crate`, `self`, `super`
   are local. A name that only its own crate provides (`use anyhow::anyhow;`) is no shadow.
5. A derive never makes a file UNKNOWN. A path in an attribute is an edge, also in a string under
   any key but a message key (`note`, `since`, `reason`, `rename`, `doc`, ...); a string with `::`
   that does not read is UNKNOWN. UNKNOWN, each with its reason: a macro call with a path in its
   body (the macros of `std` and `json!` are read), an exported `macro_rules!`, `include!`, a `cfg`
   or `cfg_attr` on a `mod` or `use`, a non-literal `path`, an attribute macro on a module, a
   missing or ambiguous module file, a syntax error, brackets nested deeper than 256, a file that
   two modules load, an unreadable `Cargo.toml` and a `[lib] name` that differs from the package.
6. `cfg(test)` and `cfg(feature = "x")` of a declared feature are read as true, so the edges are the
   union over all features. Test code is production code here until 5b-2 marks the scope.
7. The profile copies the unsupported rules of TypeScript and adds `interface_boundary`.
   `crate_scope.py` makes each scope that needs the edges inside a crate UNKNOWN until 5b-2: a
   component or rule field that names a module below a crate root, and a module-level cycle rule.
   A test over the catalog of rule and component fields fails for a new kind or field until a
   person reviews it. A profile must declare `crate_edges_only`, with no default.
8. The host uses the bundled binary as the default collector (`archkeel/_native`, `cli/observe.py`);
   without it `Language.RUST` reports `missing_tool`. A configured `collector_argv` wins. A third
   binary joins the platform wheels (AD-317), and `archkeel-build-support` holds the `build.rs` digest.
9. The scan runs in a thread with a stack of 256 MiB, so no file ends the whole scan. Every read
   goes through `archkeel-snapshot`, the one owner of paths, symlink rules and limits: a path that
   leaves the snapshot is never read. The reply is typed with `archkeel-facts` (AD-345).
10. The contract of `native/` has the components wire, snapshot, facts, build, typescript and
    rust, the rules `complete_assignment`, `complete_requires`, `no_component_cycles`, and the use
    of `tree_sitter*` and `syn`. `make self-validate-native` runs it. A planned crate joins the
    contract when it has code: with a planned component the host leaves `requires` UNKNOWN.

**Safety net.** No list of path places is complete. A bare name without `::` in ordinary Rust cannot
be a crate. So one pass reads macro bodies, attribute streams and strings: a reachable crate that
is named there and has no edge in the file is UNKNOWN. Accepted cost: 57 cases on uv.

**Reason.** The product must check its own Rust, and layering must have one owner: the contract.
**Rejected.** `tree-sitter-rust`, rust-analyzer, `cargo metadata` at run time, a model of Rust
name resolution (three false PASS). **Limit.** Crate edges only; no macro expansion, no `build.rs`
output; `init` and `explore` do not support Rust. **Check.** `cargo test`; the Rust tests of
`tests/test_collector_native_rust*.py` and `tests/test_collector_false_pass_full.py`.

**Amendment, 2026-11-10 (review of #916).**
- A dependency that a manifest declares is a crate edge: normal, dev, build, the underscore forms,
  `[target.*]`, renames, `workspace = true`, optional. A crate cannot use a crate that it does not
  declare, so this over-approximates what source hides in a macro or a generated token. The edge
  starts in a module `<crate>.cargo_toml` and cites the line of the manifest. A forbidden declared
  dependency is FAIL also when no source uses it, so the step
  `#![deny(unused_crate_dependencies)]` before 5b-3 is no longer needed. A dependency table or form
  that the reader does not know is UNKNOWN. The section is in the specifier until 5b-2.
- (a) A `macro_rules!` that stays in the crate is read as code of its file. (b) The name of an
  attribute in a macro body is a derive helper. (c) `macro_use` on a module and
  `cfg(any(test, feature = ...))` of known conditions are read. (d) A planned crate is no component.

**Amendment, 2026-11-10 (5b-2c).** Module edges, no `crate_edges_only`, a re-exporting module is the
dependency: [Rust module edges](../rust-module-edges.md). 5b-3: components by responsibility. 5b-4a: definitions and visibility ([AD-351](ad-351-the-rust-collector-reports-definitions-and-never-invents-one.md)).
