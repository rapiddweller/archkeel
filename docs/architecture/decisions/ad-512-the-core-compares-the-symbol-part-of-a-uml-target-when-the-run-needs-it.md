# AD-512 The core compares the symbol part of a UML target when the run needs it

**Status.** Proposed. Part of #880. It extends AD-494. PR 1 of 5 (L-173).

**What 4.0.1 compares** (`ir/source_graph.py`, `check/uml_compare.py`): each symbol entity of a
target against the symbol table of the source: kind, lexical parent, signature, visibility,
modifiers, annotation and initializer. Each call, reference, base, `creates` and `instance_of`
relationship is compared with the resolved edges. A closed scope fails for an unlisted definition
or resolved site. A table that 4.0.1 refuses (`ValueError`) decides nothing.

**Decision.**
1. One owner, `Usable::needs` (`native/core/src/contract.rs`), gives a typed `Needs` value. Only a
   UML target that the core compares gives `Need::UmlTarget`. A new reason is one more `Need`.
2. Without a need, no symbol table exists. The reply part, the frame and the report are the same
   bytes as before. The collector request does not change in this PR.
3. `native/model/src/symbol_table.rs` builds the table from the `SymbolFact`, `CallFact`,
   `ReferenceFact` and `BindingFact` records with `symbols.rs`, `symbol_sites.rs` and
   `symbol_values.rs`. They name no language. A profile states its own traits in
   `native/facts/src/profile_traits.rs`: `symbol_facts` (a gap, not an empty table, when false)
   and `separates_type_namespace`.
4. A profile without symbol facts (Python, Dart and Rust today) gives the named gap "the
   `<language>` collector states no symbol facts". A module that the collector cannot read keeps
   the coverage gaps of the run. The core never reads a missing section as an empty one.
5. Status is the 4.0.1 status or stricter. A missing symbol, call or reference is UNKNOWN. FAIL
   needs a conflict (kind, parent, signature, visibility, annotation, initializer), a missing base
   with complete base coverage (`Scope::uml_run` and the receipt of each class inside), or an
   extra element of a closed scope. PASS needs one resolved match for each assessment and
   `Scope::uml_complete`. An ambiguous or partial case is UNKNOWN with a named cause.
6. A table that 4.0.1 refuses (an alias or macro kind, an ambiguous source scope, a candidate
   count below the targets, an unresolved site with candidates, a construction that conflicts
   with its call) is `broken`: each symbol assessment is UNKNOWN.

**Stricter than 4.0.1 (the core is UNKNOWN, 4.0.1 passes).**
- A closed scope without an unlisted element (the `closed-method-listed` plant). 4.0.1 reads
  complete member inventories of TypeScript; the core proves no complete symbol inventory.
- A call that is absent is UNKNOWN. 4.0.1 marks calls complete when the profile measures them,
  and it could give FAIL. It gives UNKNOWN on the `missing-call` plant, so no plant differs.
- Fixture rows H-uml and H-uml-dart (4.0.1 PASS): the Python and Dart collectors give no symbols.

**Fixture rows (PR 1 moves none to PASS).** Core / 4.0.1: H-typescript UNKNOWN (9 undecided) /
UNKNOWN (9). H-uml-typescript UNKNOWN (3) / UNKNOWN (3). H-uml UNKNOWN / PASS. H-uml-dart UNKNOWN
(mounted) / PASS. I-flutter-shop, J-compass, K-python-realworld and L-nest-realworld UNKNOWN
(mounted target) / UNKNOWN.

**Cost** (release core, median of 9 runs, own throwaway root target, inside targets removed).
Without a need and with the root target: L-nest-realworld 68 ms and 23.0 MiB, then 76 ms and
24.9 MiB; H-uml-typescript 32 ms and 15.9 MiB, then 34 ms and 16.6 MiB; K-python-realworld
50 ms and 10.0 MiB, then 55 ms and 12.7 MiB. The `native/` self run has no symbol facts, so the
need adds no table: 0.7 s and 93 MiB in both cases. The reply does not change; the frame grows
by about 350 bytes for the row.

**Reason.** The row was UNKNOWN for each symbol entity. TypeScript targets can now give FAIL for
a true conflict. PR 2 to 5 add the Python and Dart facts and the `dependency_symbols` selector.

**Rejected.** A new record kind for symbols (the five record kinds exist). A flag for each
reason (one `Needs` value). A PASS where 4.0.1 passes on partial coverage.

**Limits.** No Python or Dart symbol is compared. Three guards have no TypeScript plant: a
placeholder entity (`refscope`) that is no definition, the `broken` table, and the call of the
base receipt (its function has Rust unit tests). A table is built for each run with the need.

**Tests.** `tests/test_cli_core_uml_symbols.py` (36 plants with the 4.0.1 row and the cause of
each row), `tests/test_cli_core_uml_needs.py` (a run with a target differs from a run without
only by the row), `tests/test_cli_core_uml_target.py`, and the Rust tests of `contract_tests.rs`
and `uml_symbols_tests.rs`.
