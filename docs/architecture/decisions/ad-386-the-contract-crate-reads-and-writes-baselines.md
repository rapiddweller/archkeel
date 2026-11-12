# AD-386 The contract crate reads and writes baselines

**Status.** Accepted. Part of #880. It extends [AD-375](ad-375-the-contract-crate-reads-amendments-and-binds-them-to-a-comparison.md).

**Decision.** `policy::parse_baseline` reads bytes without file access or a workspace dependency.
It returns typed violations, fingerprints, roles, scalar budgets and keyed name budgets.
`baseline_bytes` writes schema 1.3.0 with the bytes of Python `baseline_bytes`.
`baseline_digest` hashes these bytes, not the input bytes.
The Python source is `ir/codec_governance.py`, with `codec_wire.py` and `measurements.py`.

**Format.** Read schema 1.0.0, 1.1.0, 1.2.0 and 1.3.0.
The root has exactly `schema_version`, `violations`, and, from 1.2.0, `budgets`.
A violation has exactly `rules`, `subjects`, `count`, and optional `roles` from 1.1.0.
A count is a positive integer. Rules and subjects are string arrays.
A role has exactly `source` and `target`, both strings. Repeated roles fail.
A repeated canonical fingerprint fails, even if its roles or count differ.
Budgets are the six scalar names of Python, with non-negative integer values.
Schema 1.3.0 also reads `facade_names` and `coupling_names` objects.
Each key must not be blank for Python `str.strip`. Each value lists sorted unique strings.
Errors keep the Python validation order and messages for supported value representations.

**Python oddities, ported literally.**
1. Sort rules and subjects, but keep repeated strings. An empty list or string is valid.
2. Roles carry direction separately. Empty role strings and roles outside the subjects are valid.
3. Validate all entries before checking repeated fingerprints, then validate budgets.
4. Sort roles and violations. Omit empty roles on write. Upgrade every read version to 1.3.0.
5. Keep empty strings in accepted names. Validate names before checking a blank budget key.
6. Sort budget kinds and keys before validation. Empty keyed objects disappear on write.
7. Use Python white space, including U+001C through U+001F, for a blank key.
8. Do not check rule existence or staleness in the codec. Keep every valid entry.
   Python later reports stale entries as resolved debt; the codec does not discard them.

**Named refusals, stricter than Python.**
- `DuplicateKey`: refuse a repeated JSON key at every level. Python keeps the last value.
- `Json`: refuse lone surrogate escapes and NaN/Infinity tokens. Python can decode them.
- `TooLarge`: refuse input over 16 MiB before parsing. Python has no byte limit.
- `Json`: keep the existing JSON reader's depth limit of 128. Python can read deeper input.
- Integer range: refuse counts outside `u64`. Python integers have no fixed width.
  The shared reader gives `NotCount` or `Json` for larger tokens; no conversion truncates them.
- Unsupported schema types use the amendment codec's bounded type markers in errors.
  Python can raise `TypeError` for an unhashable schema. Neither side gives a decoded baseline.

**Reason.** A lost baseline entry or accepted invalid file can permit a false PASS later.
Typed private fields prevent callers from building unchecked values.

**Rejected.** Deserialize directly into maps; ignore unknown fields; sum repeated entries;
apply baselines in this slice; take a digest from the caller; copy the JSON writer.

**Scope and limit.** No change to Python behavior, `eval`, `model`, `report` or `core`.
No filesystem loader, containment check, verdict application, widening or amendment binding.
The existing `Baselines::configured_unsupported()` refusal stays in place.
No command uses this codec yet. The shell must map a read error to a named refusal.
The API tool on this base has no writer. Add `--write` to record its measured counts.
This does not change the API counting rules; the open API-list slice can replace it later.

**Tests.** `native/contract/src/policy/baseline_tests.rs` checks the grammar and bounds.
`tests/test_rust_contract_baseline_parity.py` compares repository, demo and hostile bytes
with the unchanged Python reader and writer. The PR records isolated injected faults.
