# AD-375 The contract crate reads amendments and binds them to a comparison

**Status.** Accepted. Epic #880, M6b contract lane 3. It extends [AD-373](ad-373-the-contract-crate-compares-two-contract-trees-for-against.md).

**Decision.**
1. `policy::parse_amendment` and `policy::amendment_bytes` read and write schema 2.0.0 as Python
   `parse_amendment` and `amendment_bytes` do: the seven keys exactly, 64 lowercase hex digits for
   each digest (a baseline digest can be `null`), texts not blank for Python `str.isspace` (which
   holds U+001C to U+001F; Rust `char::is_whitespace` does not). The checks, their order, the
   messages and the bytes are those of Python.
2. `policy::bind(old, after, baselines)` keeps the comparison and the four digests that an
   amendment must hold: the `comparison_digest()` of each tree, never the bytes of `Comparison`
   (its serde form leaves out the direction). The old side is a tree or `OldContract::Introduced`
   (AD-104); then the crate makes the `presence` change and `absent_contract_digest(path)`.
3. `Binding::check` gives `Unchanged`, `Covered` (Python `valid`), `Unamended` or `Stale`, with the
   failures of `_widening_failures`. A stale amendment fails also when nothing widened.
4. Type barrier: a `Verdict` comes only from `check`, a `Binding` only from `bind(&ContractTree)`,
   an `Amendment` only from `parse_amendment` or `Binding::amend`. Doctests in `binding.rs` prove it.
5. The baseline fact (lead decision L-34a). Python binds baseline digests that it computes from
   the baseline content; the crate has no baseline codec. The shell must state the fact:
   `Baselines::not_configured()` or `Baselines::configured_unsupported()`. For the second, `bind`
   gives `BindError::BaselineNotSupported`: no verdict, never `Covered` or `Unchanged`.
6. `json::read` finds a repeated key with a set: O(n log n) for 10^6 keys, not O(n^2).

**Decision: schema 2.0.0 only (lead decision L-34b).** It overrides table D and row 3 of the M6b
proposal ("read both, write v2"). Reason: schema 1.0.0 binds no baseline, and Python accepts it
only for a run without `--baseline` and with equal contract digests. The repository holds 3 v1
files (`ad-121`, `ad-123`, `ad-126`), and no gate reads them; it holds 97 v2 files. No fixture or
demo holds v1; Python tests build v1 only to test the Python reader. Effect after Cut A: a v1
amendment gives exit 2 where Python can pass; the message names
`archkeel validate --against <ref> --amendment <path> --write-amendment --decided-by <who> --rationale <why>`.
Undo: port the v1 reader.

**Stricter than Python.** Rust refuses; Python accepts: schema 1.0.0; a repeated JSON key (Python
keeps the last value); a lone surrogate escape (Python cannot write it again); a blank text in
`Binding::amend` (Python writes a file that its reader refuses); nesting deeper than 128 levels
(Python raises `RecursionError` and gives no verdict).

**Reason.** An amendment that Rust accepts and Python refuses is a silent false PASS of the
governance gate.

**Rejected.** Bind the serialized `Comparison`: two comparisons with other directions have the
same bytes. A baseline digest as a text from the caller. Keep the last value of a repeated key.

**Limit.** A run with `--baseline` gets no Rust decision until the baseline codec (M6b row 2)
adds the digests and the baseline and budget widenings. The crate cannot check that the old
revision holds no contract at a path. Rename recognition (AD-105) is not ported (AD-373): Rust
reports widenings where Python sees a rename. `native/core` does not call `bind` yet. The
messages equal those of Python 3.11 (L-28).

**For the wiring PR.** The request carries the baseline fact as a required field. A path reaches
the crate as `&str`: the shell must refuse a Git path that is not UTF-8 with a named error
(Python fails there with `UnicodeEncodeError`).

**Next PR.** The baseline codec (read 1.0.0 to 1.3.0, write 1.3.0), a `Baselines` constructor
from the baseline that the crate writes, and the baseline widenings.

**Tests.** `tests/test_rust_contract_amendment_parity.py` with
`tests/rust_contract_amendment_cases.py`; `native/contract/src/policy/amendment_tests.rs`; the
doctests of `native/contract/src/policy/binding.rs`.
