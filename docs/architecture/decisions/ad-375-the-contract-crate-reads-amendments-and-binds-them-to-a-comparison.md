# AD-375 The contract crate reads amendments and binds them to a comparison

**Status.** Accepted. Epic #880, M6b contract lane 3. It extends [AD-373](ad-373-the-contract-crate-compares-two-contract-trees-for-against.md).

**Decision.**
1. `policy::parse_amendment` and `policy::amendment_bytes` read and write an amendment of schema
   2.0.0 as Python `parse_amendment` and `amendment_bytes` do: the seven keys exactly, each digest
   64 lowercase hex digits (a baseline digest can be `null`), `decided_by` and `rationale` not
   blank for Python `str.isspace` (that set holds U+001C to U+001F; Rust `char::is_whitespace`
   does not). The checks run in the Python order with the Python messages. The bytes are sorted,
   indented by 2, with non-ASCII text unescaped and a line feed at the end.
2. `policy::bind(old, after, baselines)` makes a `Binding`: the comparison and the four digests
   that an amendment must hold. The old side is an assembled tree or `OldContract::Introduced`
   (AD-104). For the second, the crate makes the one `presence` change with the message bytes of
   Python and `absent_contract_digest(path)`. The digests are `comparison_digest()` of the trees,
   never the bytes of `Comparison`: its serde form leaves out the direction and the kind.
3. `Binding::check(amendment)` gives a `Verdict`: `Unchanged`, `Covered` (Python `valid`),
   `Unamended` (no amendment) or `Stale`, with the failure messages of `_widening_failures`. A
   stale amendment fails also when nothing widened. An amendment that cannot be read is an
   `AmendmentError`, so it is not a verdict. `Binding::amend` writes the covering amendment.
4. Type barrier: a `Verdict` comes only from `Binding::check`, a `Binding` only from `bind`, which
   takes `&ContractTree` (only `assemble_tree` makes one), and an `Amendment` only from
   `parse_amendment` or `Binding::amend`. Compile-fail doctests in `binding.rs` prove each step.
5. Baseline digests: Python computes them from the canonical bytes of the parsed baseline, and
   for the new side from the observed violations. The crate has no baseline codec, and a digest
   string from the caller would let a caller pass without the content. So only
   `Baselines::not_configured()` is public. A run with `--baseline` cannot be bound in Rust yet.
6. The repeated-key check of `json::read` uses a set: an object with 10^6 keys costs O(n log n),
   not O(n^2). The first repeated key is the same.

**Stricter than Python.** Rust refuses; Python accepts:
- Schema 1.0.0. Python reads it (the five keys, valid digests, texts not blank) and
  `verify_amendment` accepts it only when the run has no `--baseline` and both contract digests
  are equal. Rust gives `Version1`, so the run gives exit 2. Python writes only 2.0.0.
- A JSON object with one key two times. Python keeps the last value.
- A lone surrogate escape in a text. Python reads it and then cannot write it again.
- `Binding::amend` with a blank `decided_by` or `rationale` (for example `" "`, which the CLI
  lets through). Python writes a file that its own reader refuses.
- Nesting deeper than 128 levels. Python stops with `RecursionError` and gives no verdict.

**Reason.** An amendment that Rust accepts and Python refuses is a silent false PASS of the
governance gate. Each change keeps Rust equal to Python or stricter.

**Rejected.**
- Read schema 1.0.0 too (M6b proposal, row 3). It binds no baseline, and it covers only the one
  change that it was written for, so an old v1 file almost never meets the gate again.
- Bind the serialized `Comparison`. Two comparisons with other directions have the same bytes.
- Take a baseline digest as a text from the caller (point 5).
- Keep the last value of a repeated key. A reviewer reads the first value in the diff.

**Limit.** The baseline and budget widenings of `--against`, and the baseline digests, come with
the baseline codec (M6b row 2). Until then the core must not use `bind` for a run with a
baseline. The shell decides that the old revision holds no contract at a path; the crate cannot
check it. Rename recognition (AD-105) is not ported. `native/core` does not call `bind` yet. The
messages equal those of Python 3.11 (L-28).

**Next PR.** The baseline codec (read 1.0.0 to 1.3.0, write 1.3.0) in this crate, a `Baselines`
constructor from the baseline that the crate writes, and the baseline widenings.

**Tests.** `tests/test_rust_contract_amendment_parity.py` with
`tests/rust_contract_amendment_cases.py` (generated and 54 hand-written hostile amendments,
gates on the pairs of AD-373 with stale digests on each position, other pairs, replays,
introduced contracts, and written amendments); `native/contract/src/policy/amendment_tests.rs`;
the doctests of `native/contract/src/policy/binding.rs`.
