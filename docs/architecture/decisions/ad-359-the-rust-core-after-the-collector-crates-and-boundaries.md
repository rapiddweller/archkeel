# AD-359 The Rust core after the collector: crates and boundaries

**Status.** Accepted. Epic #880, WP6 slice 0c-1 (design WP6-0, section B).

**Decision.**
1. The owner approved this on 2026-11-11: one Rust process runs everything after the collector.
   It has seven crates: one binary (`archkeel-core`) and six libraries (`report`, `eval`, `model`,
   `contract`, `store`, `facts`). The shell sends the contract bytes and gets one Report frame.
   Milestone M1 is Cut A of the design.
2. The dependency graph points down only. `core` uses the libraries. `report` uses `eval`. `eval`
   uses `model` and `contract`. `model` uses `contract`, `store` and `facts` (amended by AD-363). `store` uses `facts`.
   `contract` uses no crate of the workspace, so a Target id can never be a source id.
3. The shell reads the root contract and each inside contract (it owns Git and the file system).
   It sends the bytes. The core reads no file.
4. Design intent, not decided here: a rule gives PASS only with a `ScopeComplete` value that only
   the scope proof of `model` can make, and a closed (rule kind, capability) table gives UNKNOWN
   outside it. Slices 0b and S4 decide these in their own records.
5. This slice adds `native/contract` (`archkeel-contract`). It parses contract bytes into typed and
   closed values: components, `requires`, the 12 structural rule kinds, the digest of the bytes and
   the canonical bytes of Python `contract_bytes`. The fields are private to the crate, so a
   `Contract` comes only from `parse`. It runs the checks in the order of `parse_contract`, so the
   first error has the same kind: `Invalid` (`ValueError`), `Version` (`ContractVersionError`) or
   `Input` (`ContractInputError`).
6. The parser stops with `Unsupported` at a part of slice 0c-2: a `declarations` object and the ten
   rule kinds that only the Python profile decides. It never skips a part.

**Reason.** The model and the evaluator (64 000 lines of `ir/` and `check/`) need the contract in
Rust. A crate boundary checks "no source id in the contract" without a review. The parity with the
Python parser lets the dual run compare verdicts, because both engines read one contract.

**Rejected.**
- serde derive on the contract structs. The grammar must tell an absent key from `null` and must keep
  the Python check order. A derive cannot give both. Only the closed enums use serde, for their words.
- A contract parser inside `store`. Then `contract` would see `facts`.
- A binary of the contract crate. The core is the only binary; the parity probe is an example.

**Limit.** Not in Rust yet (slice 0c-2): `declarations`, inside mounts and the kinds
`symbol_placement`, `source_ownership`, `boundary_types`, `protocol_declarations`, `call_owner`,
`bounded_numeric_operand`, `forbidden_call_argument`, `catalog_argument`, `catalog_use`,
`forbidden_effect_under_condition`. Rust is stricter than Python in these cases:
- A repeated JSON key is `DuplicateKey` (as #982). Python keeps the last value.
- `"declarations": {}`: Python accepts it; Rust stops with `Unsupported` until 0c-2.
- A lone surrogate escape: Python parses it, then `contract_bytes` fails with
  `UnicodeEncodeError`. Rust refuses it as invalid JSON.
- An integer above 2^64: `serde_json` reads it as a float, so only the `line` check refuses it
  ("must be a positive integer"). Python accepts it.
- The XID tables of `unicode-ident` and of the Python release can differ for a new character.

**Tests.** `tests/test_rust_contract_parity.py`: `test_the_rust_parser_decides_each_contract_as_python_does`,
`test_a_repeated_key_is_refused_in_rust_and_kept_last_in_python`,
`test_a_declarations_object_and_a_python_only_rule_are_unsupported_by_name`;
`native/contract/src/contract_tests.rs`.
