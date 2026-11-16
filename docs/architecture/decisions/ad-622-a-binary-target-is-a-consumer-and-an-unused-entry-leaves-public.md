# AD-622: A binary target is a consumer, and an unused entry leaves public

Status: accepted (owner order). Part of #880. It amends AD-514 and AD-608.

## Context
On main `de6d2baa7` the system gate was UNKNOWN. The native self-check had 23
`interface.usage_unknown` gaps (24 after #1307) and one UNKNOWN rule (`interface_boundary: unread import binding`).
The UNKNOWN rule was hidden earlier, behind the publication FAIL rows of AD-608. After #1263 the
system run was also refused: its frame lost the premise of the Python part.

## Decision
1. A `public` entry that no import of another component names, by any route (a glob into the crate
   included), leaves `public`. The type stays usable through the function that returns it. This
   removes 20 entries of `model` and `eval::BoundaryViolation`, and `collect::SystemInterface`
   (#1307; `core` reads it only as a field of `System`), which also leaves the root re-export of
   `collect` and the port of `core-requests`. The interface rule judges each later import against
   the smaller list, so the removal can give a FAIL and never a wrong PASS.
2. Each target of a Cargo package (library, binary, build script) is a crate of its own. The Rust
   collector records the target of each module and states `other_crate` on an import that names a
   module of another target or another crate of the workspace. The usage check of contract hygiene
   counts such an import also inside one component: the library publishes the name for that crate
   (AD-608). This proves the uses of `dart::decode` and `typescript::reply` by `src/main.rs`.
3. The root of `contract` re-exports its 38 used types by name, not by five globs (`pub use
   model::*`). The scan cannot read the names of a glob of types that macros define, so AD-608 left
   each glob UNKNOWN. The other 50 types are no longer published: no other crate uses them (the
   workspace builds with all targets).
4. The system frame keeps the premise of each part (AD-540), each once, joined by `; `.
5. The marked graph of `docs/architecture/native.md` draws the observed edge `report -> report-frame`.

## Results
Native self-check: 86 PASS, 0 gaps. System gate: PASS (shell 23 rules, core 86 rules).

## Tests
- `tests/test_cli_native_rust_binary_use.py` (rustc accepts each plant): a binary of the package
  uses the entry, so it has no usage gap; with no use, or only a use in the library itself, the gap
  stays.
- `native/core/src/system_tests.rs`: the system frame keeps each premise once.
