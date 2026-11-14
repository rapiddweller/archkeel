# AD-512 The core compares the symbol part of a UML target when the run needs it

**Status.** Proposed. Part of #880. It extends AD-494. PR 1 of 5 (L-173).

**What 4.0.1 compares** (`ir/source_graph.py`, `check/uml_compare.py`): each symbol entity of a
target with the symbol table of the source: kind, lexical parent, signature, visibility,
modifiers, annotation and initializer. Each call, reference, base, `creates` and `instance_of`
relationship is compared with the resolved edges. A closed scope fails for an unlisted definition
or resolved site.

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

**Where the core differs from 4.0.1 (95 plants: 45 equal, 45 PASS to UNKNOWN, 5 FAIL to UNKNOWN).**
- Wrong 4.0.1 PASS (44 plants). A scope below the module that declares the name of a site hides
  the module symbol. This holds for a function, class, interface, type alias, enum, type
  parameter or catch binding, a declarator, a `for` head, and every name of a pattern (shorthand,
  renamed, array, rest, default, nested). One index (`site_local.rs`, `NameIndex::locally`)
  serves each site kind and each base; `pattern_names` is the one reader of a pattern. A site, or
  a base, with such a name is unresolved: UNKNOWN with the cause "unresolved ... site". A name
  that is written more than once keeps no result binding (UNKNOWN): the writes are a second
  declarator, a pattern, an operator (`+=`, `&&=`, `++`) or a `for` head, read by
  `written_by`. A member of an ambient module or a namespace is no symbol of the file.
- A closed scope without an unlisted element is UNKNOWN (`closed-method-listed`).
- FAIL to UNKNOWN (5 plants, `member-*`): a planned member that the matched class lacks is FAIL
  in 4.0.1 and "absent symbol" in the core: a plain constructor parameter, a `#x` field, an enum
  literal, a member that a decorator makes, a method of a class and namespace merge. The core
  states no member that the collector cannot name. A complete member table of the class would
  allow FAIL: no syntax of the class (computed names, decorators, merges) may make a member that
  the collector does not name.

**Fixture rows (PR 1 moves none to PASS).** Core / 4.0.1: H-typescript UNKNOWN (9 undecided) /
UNKNOWN (9). H-uml-typescript UNKNOWN (3) / UNKNOWN (3). H-uml UNKNOWN / PASS. H-uml-dart UNKNOWN
(mounted) / PASS. I-flutter-shop, J-compass, K-python-realworld and L-nest-realworld UNKNOWN
(mounted target) / UNKNOWN.

**Cost** (release core, median of 9): L-nest-realworld 68 ms and 23.0 MiB without a need, 76 ms and
24.9 MiB with it; other runs 2 to 5 ms more. The `native/` self run builds no table.

**Rejected.** A new record kind for symbols. A flag for each reason (one `Needs` value). A PASS
on partial coverage. A FAIL for a member that the collector does not name.

**Limits.** No Python or Dart symbol is compared. Two guards have no TypeScript plant: a
placeholder entity (`refscope`) that is no definition, and the `broken` table. A table is built
for each run with the need. Named, not fixed: an undrawn extra in a closed scope stays UNKNOWN
for a call through `this`, an alias, a decorator, a computed member, `new` through a variable,
an arrow field, a class expression or a default-export function.

**Tests.** `tests/uml_symbol_*.py` with `test_cli_core_uml_symbols.py` (95 plants, the 4.0.1 row and
the cause of each row), `test_cli_core_uml_needs.py`, `test_cli_core_uml_target.py`, and the Rust
tests of `contract_tests.rs`, `uml_symbols_tests.rs` and `site_names_tests.rs`.
