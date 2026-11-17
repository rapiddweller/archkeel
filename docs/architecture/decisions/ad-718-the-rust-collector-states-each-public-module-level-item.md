# AD-718 The Rust collector states each public module-level item

**Status.** Accepted (lead order: release gate 1 needs 0 UNKNOWN). Part of #880, closes #1450. It amends AD-351 and AD-670 item 5.

**Reason.** `NATIVE-PUBLIC-HAS-A-USER` (`unused_public`) was UNKNOWN on main: "the collector does not state every public symbol". The hold was not a gap with a place. `limits.rs` held the rule whenever the profile flag `symbol_facts` was false, and that flag means symbols, calls and references for UML, which Rust does not state. Under it, three constructs were not stated:
- the items of an `extern` block;
- the public items that a module-level call of a workspace `macro_rules!` writes;
- an item that syn cannot parse.

**Decision.**
1. A new profile flag `public_symbols` says that the collector states each public module-level item that it reads, and gives a gap or a record with an unread name for each one that it cannot read. It is true for TypeScript, Python and Rust. `unused_public` needs it for a PASS, in place of `symbol_facts`.
2. The `pub fn`, `pub static` and `type` of an `extern` block are definitions of the module.
3. A module-level call of a workspace `macro_rules!` writes the public items of the arms that its input can match. An arm can match only when the leading literal tokens of its matcher agree with those of the input; an item-level self-call of an arm counts as an input. An item is public by a literal `pub` and its keyword. It may be public by a `vis` metavariable, which is public only when the call holds a bare `pub`. A metavariable at the start of an item (`$($t)*`, `$pub $struct $name`) may write items of the call tokens. Then each `pub [qualifiers] keyword name` of the call tokens is an item, and a field `pub name:` is not.
4. An item with a literal name and kind is a symbol record with the call as its evidence. One whose name or visibility the call gives, an inline `mod`, or a `pub` before a metavariable keyword, is a record of its kind (or of no kind) with the visibility basis `macro_call`. `unused_public` judges it undecided, and an item of no kind is never left out by `item_kinds`.
5. An item that syn cannot parse (`Item::Verbatim`) is a gap at its place.

**Why it is sound.** A public module-level item of a Rust crate comes from four sources: an item that the scan reads, an `extern` block, a macro expansion, or code that the scan does not read. Procedural and foreign macros, attribute macros, unproved derives, `include!` and module files that the scan does not read keep their gaps (AD-662 and the expansion gaps), and each gap holds the rule (AD-670 item 6). A workspace macro gives its items by items 3 and 4.

**Measured.**
- Native self-check: 91 PASS / 0 FAIL / 1 UNKNOWN before, 92 PASS / 0 FAIL / 0 UNKNOWN after. `rules!` writes `$inner fn body_of` with `pub(crate)`, so it is no public item.
- Oracle: rustdoc JSON (`--document-private-items`) of itoa 1.0.19, memchr 2.7.5 and syn 2.0.119 lists 2, 51 and 529 public module-level items. Each one is stated or has an unread-name record in its module. Before the call-token rule, syn had 190 items missing.
- The `unused_public` verdict on the same crates is the same on main and here: UNKNOWN, FAIL with 8 rows, FAIL with 572 rows. No PASS.

**Tests.** `native/rust/src/public_items_tests.rs`, `tests/test_cli_native_unused_public_constructs.py` (rustc accepts each plant), `symbols_tests.rs` (the item that `$t:item` writes is stated now).
