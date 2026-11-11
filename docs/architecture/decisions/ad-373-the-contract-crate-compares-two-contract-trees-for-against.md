# AD-373 The contract crate compares two contract trees for --against

**Status.** Accepted. Epic #880, M6b contract lane 2. It extends [AD-366](ad-366-the-inside-contract-tree-is-assembled-and-checked-in-the-contract-crate.md).

**Decision.**
1. `policy::compare_trees(before, after)` compares two assembled trees as `validate --against`
   does: the widenings of `contract_widening_changes` between the comparison contracts, then the
   widenings of the declarations of each inside scope (`_inside_declaration_widenings`), then the
   narrowings of `contract_narrowing_changes` (AD-255). `Comparison::widened()` is the decision.
2. Each change has a direction, a closed `ChangeKind`, and the subject, field and message of
   Python, byte-equal. A message keeps the Python `repr` of each value; the characters that
   `repr` escapes come from a table that `tools/contract_printable.py` writes from Python 3.11
   (Unicode 14), as L-27 does for the Dart collector (L-28).
3. The comparison fails closed as Python does. A component or rule field that no classifier names
   is compared on its canonical value, so a new field widens until a classifier names it; a value
   that serde cannot give as an object widens too. The other declarations are named in a pattern
   without `..`, and the classified rule kinds in a `match` over `RuleKind` without a catch-all,
   so a new field or kind does not compile without a decision. A kind without a classifier widens
   on any difference, also of its rationale.
4. The comparison cannot fail: the trees are complete (AD-366), so it returns a value, not a
   `Result`.

**Reason.** `--against` is a CI gate of user projects: a widening that Rust misses is a false
PASS. The comparison reads only two contracts, so it fits the contract crate, which uses no
workspace crate (M6b proposal, row 3).

**Rejected.**
- A typed field list for each record in place of the canonical value. A new field would pass as
  neutral until someone adds it to the list.
- Messages with Rust text. The result of a command shows them, and the dual-run oracles compare
  them.

**Limit.** Rename recognition (AD-105) is not ported (M6b row 4): a moved package shows as
widenings. The baseline and budget widenings of the baseline file and the amendment codec and
its binding to the digests come in the next PR of the lane. "No contract at the old revision"
stays in the shell for now. Rust refuses a contract with one JSON key two times (AD-364), so such a pair
gives no comparison. Rust refuses an integer of 2^64 or more (AD-359), so such a pair gives no
comparison; Python compares it. The message bytes equal those of Python 3.11: on Python 3.12 or
later a code point assigned after Unicode 14 gives other message bytes. No decision depends on a
message.

**Next PR.** `Comparison` serializes without the direction and the kind of a change. The amendment
binds `comparison_digest()` only, not the comparison bytes. "No contract at the old revision"
(AD-104, `_Introduced` in Python) is decided in the crate, for example as
`compare_introduced(after)`, together with `absent_contract_digest`.

**Tests.** `tests/test_rust_contract_against_parity.py` with `tests/rust_contract_against_cases.py`
(the 15 `demo--against-*` recordings, hand-written changes, one changed key of each role in both
directions, two changes together, inside trees, 40 `repr` probes in two fields);
`native/contract/src/policy/compare_tests.rs`; `native/contract/src/policy/printable_tests.rs`.
