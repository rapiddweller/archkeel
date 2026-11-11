# AD-361 The Rust contract parser reads the whole grammar

**Status.** Accepted. Epic #880, WP6 slice 0c-2. It extends [AD-359](ad-359-the-rust-core-after-the-collector-crates-and-boundaries.md).

**Decision.**
1. `archkeel-contract` parses each part of `parse_contract`: the 22 rule kinds, the
   `declarations` object (capabilities, review scopes, public API, commands, context roots,
   paths, SPOT owners, compatibility shims, measurement, facade and coupling budgets, module
   targets) and the UML Target of `declarations.uml`. The error kind `Unsupported` is removed.
2. With a UML Target, the parser runs the checks of `declared_graph` in the Python order:
   `intent_graph`, `ArchitectureGraph.validate`, the reference link of `_link_references` and
   the check again with the `requires` relationships. It keeps no graph, only the errors.
3. Python reads the declarations in three steps: capabilities before the components, the other
   records after them, and the four string lists after the label checks. The Rust parser keeps
   these steps, so the first error of a contract has the same kind.
4. The canonical bytes come from `serde::Serialize` on the contract types. Each type has the field
   order of its dataclass, and serde attributes leave out what `contract_bytes` leaves out. The UML
   Target keeps each `null`, as `asdict` writes it.
5. Each repository contract parses. The self contract, `native/architecture-contract.json` and
   the inside contracts give canonical bytes and digests equal to Python.

**Reason.** The model and the evaluator need every rule and every declaration in Rust. An
`Unsupported` stop would leave the Python parser as the only reader of most real contracts.

**Rejected.**
- Keep a graph of the UML Target in the parser. No reader needs it yet; slice S4 builds the
  model graph from the typed contract.
- Hand-written canonical writers for each type. Their field lists repeat in one shape, and a
  derive keeps the order in one place.

**Limit.** The inside contract tree (`codec_inside.py`: mounts, paths, depth, identity) is not in
Rust; the shell still assembles it, and slice 0b or a later slice decides its frame. The ids of
`stable_id` use a Python `repr` that covers printable text and ASCII control characters; another
Unicode character that Python does not print can give another id. The stricter cases of AD-359
stay; `docs/known-limits.md` lists them.

**Tests.** `tests/test_rust_contract_parity.py` (the repository, mutations of each optional key of
each role, and the graph cases of `tests/rust_contract_graph_cases.py`);
`native/contract/src/uml_tests.rs`; `native/contract/src/contract_tests.rs`.
