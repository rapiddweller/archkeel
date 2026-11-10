# AD-351 The Rust collector reports definitions and never invents one

**Status.** Accepted. Slice 5b-4a of issue #880. It amends
[AD-335](ad-335-archkeel-checks-the-rust-of-native-with-its-own-contract.md) and refines
[AD-349](ad-349-the-template-of-a-macro-is-an-edge-of-its-calls-and-a-kind-of-its-own.md).

**Decision.**
1. The collector writes a `symbols` section. Each definition of production code is one record:
   `fn` (function), `struct` and `union` (class), `enum` (class, with its variants), `trait`
   (class of kind protocol: the report shows an interface), `const` (constant), `static`
   (static constant), `type` (type alias) and `macro_rules!` (the new kind `macro`).
2. A `fn` and a `const` of an inherent `impl` are members of the type. A `fn` of a `trait` is a
   member of the trait and has the visibility of the trait. `impl Trait for T` gives no
   definition: the trait declares the members. A `mod` stays a file fact.
3. Visibility: `pub` is `public`; `pub(crate)`, `pub(super)`, `pub(in path)` and an unexported
   `macro_rules!` are `package`, with the spelling; no keyword and `pub(self)` are `private`.
4. A member has a place only when its type is a definition of the same module and scope. Any other
   member is not read. A macro call at item level gives no definition. Nothing is invented.
5. Each class record carries two member receipts, both `partial`, so that the graph reports the
   inventory as partial. An item inside a function body is no definition. A `cfg(test)` item is no
   definition when the request excludes tests.
6. The kind `macro` is new in facts schema 9 (`Kind`, `SymbolCategory`, `SymbolFact::Macro`) and in
   the host (`EntityKind.MACRO`). Schema 9 is in no release tag (AD-349), so it may change.
7. The Rust profile produces `symbols` as an optional section; references, bindings and calls stay
   absent. `interface_boundary` stays unsupported (5b-4b).

**Problem.** The report of `native/` showed modules and edges, but not which items a module offers.

**Rejected.** (a) A gap for each item that the scan cannot read: any gap makes the scan incomplete
(exit 2), and every real crate has a macro that defines items, so no report could be complete. (b)
`rustdoc` at run time: it needs a nightly flag and a build. (c) A guess at the type of an `impl`
by its name in another module: it is the work of 5b-4b, with the module index.

**Limit.** The definitions that the scan does not read are not marked per module. The member
receipts and the partial coverage of the graph say it. A method of an `impl` in another module
than its type (`impl Builder` in `edges.rs`, `Builder` in `builder.rs`) is missing. Fields are not
read. The `rustdoc` oracle lists both differences.

**Tests.** `symbols_tests.rs`, `schema_tests.rs`, `tests/test_collector_native_rust_symbols.py`
and `tests/test_collector_native_rust_definitions_oracle.py` (the definitions of `native/` equal
`rustdoc --output-format json`).

**Conditions of 5b-4b (2026-11-10).** `interface_boundary` stays unsupported for Rust until
slice 5b-4b ships all of these:
1. A count of unread items for each module: macro calls at item level, and `impl` blocks whose
   type was not found. The explorer shows it next to the symbol count.
2. Reachable visibility, not only the `pub` keyword. A `pub` item in a private `mod`, or only
   reachable through a `pub(crate) use`, is not public API.
3. A rule reports UNKNOWN for a module with unread items. It never reports PASS.

**Follow-ups of the oracle.** Pin the 36 methods that the collector lacks. Rustdoc cannot tell
`pub(crate)` from private at the crate root, so the oracle reads it as private.

**Schema.** The entity kind `macro` is valid only for graph, report and target schema 1.3.0. A
document of 1.0.0 to 1.2.0 with this kind is invalid, as for `planned` (#854).

