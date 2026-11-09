# AD-340 The native records are built behind the dump and reach the wire last

**Decision.** PR 4.3a-3 of issue #880 (the records of the native TypeScript collector) is four PRs.
The records are built and compared with the unmodified Python collector first. The reply stays the
legacy reply of AD-320 (sections `imports` and `unknowns`, no construct capability) until the last
PR, so the host cannot read a new record and no verdict can change. This record extends AD-323.

1. **3a (this PR): the expanded imports and the constructs.** `records.rs` builds one `IMP_BINDING`
   record for each bound name (`_named_imports`), the `ESM_EXPORT` witnesses (`_export_binding`)
   and the `TSCONSTRUCT` records (`_constructs`). The `dump` feature prints them with
   `--dump-records`. A plain collection keeps nothing for them (`keep` is false).
2. **3b: symbols** (`TSDEF`, classifier data, bases, member inventories). **3c: calls, references and
   bindings** with the resolver. Both fill a section with `Record`; neither changes `native/wire`.
3. **3d: the streamed reply, the flip and the verdict differential.** Only 3d moves the records into
   `Facts.sections` and the construct capability into `Facts.constructs`, declares the inner-UML
   capability, and runs the verdict test against the default collector.
4. **The wire has every type now.** `Record` has `fact_ids`. `Facts.sections` holds any section by
   name (`imports`, `symbols`, `calls`, `references`, `bindings`, `constructs`), and
   `Facts.constructs` holds the construct capabilities. A test encodes all six sections.
5. **Evidence apart.** The evidence that the new records cite is kept in the dump, so the evidence
   of the reply does not change. 3d merges it.

**Oracle.** `tests/test_collector_native_records.py` runs the Python methods in the order of
`_Collection.facts()` up to `_constructs()` and compares imports, targets in the order of the walk,
witnesses, constructs and the cited evidence: the fixtures, the Studio UI, the resolution grid,
syntax pieces in a project, mutated projects, and further corpora (`ARCHKEEL_RECORDS_CORPORA`).

**Cost.** Python scans the bindings of a file for each statement and the exports of a module for
each bound name. `Kept` indexes both, so a file with n statements and n exports stays linear. Four
shapes (many statements, one statement, many importing files, comparisons) have a time ratio and a
memory bound. They found a loop of PR 4.2: `Snapshot::read` read and digested a file for each import
of it (n imports of a file of size m cost n times m). `readable` skips a file that was read.

**Limit.** The records are not in the reply. The Python rules for the evidence of `fact_ids` and the
order of `bindings` are 3c and 3d.

**Note, 2026-11-09 (3b): symbols.** `symbols.rs` builds one `TSDEF` record for each definition
(`_inner_symbols`, `_symbol_metadata`, `_classifier_data`, `_attribute_declaration`, `_base_record`),
and `symbol_table.rs` is the table that 3c reads: `SymbolTable::build(&Pending)`, `entries`,
`at(rel, line, column)` (`ids`), `with_qualified(name)` and `count(name)` (`by_qualified`),
`classifier_count(name)`, `scope(name, line, column)` (`scope_ids`), `top_level(module)` and
`in_module(module)`. Counts are constant time, so a name with k definitions costs k. Python scans
all definitions for each class to find its methods; a map keyed by module, parent name and position
does it once. The evidence of a location is decided by its last citation (`record_evidence`
overwrites), so `Cited` starts from the evidence of the reply and the order of the new records
follows Python: imports, symbols, then constructs. 3c cites the sites between them; the oracle
leaves those locations to 3c.

**Note, 2026-11-09 (3c): calls, references and bindings.** `site_records.rs` builds the `TSCALL`,
`TSREF` and `VALUEBIND` records (`_inner_sites` and the record builders), and `resolution.rs` is the
syntactic resolver (`_site_resolution`, `_unqualified_candidates`, `_local_import_bindings`). Python
scans the top-level definitions and the definitions of the imported module for each site, and the
members of the class for each `this` reference; the symbol table answers each with one lookup
(`top_named`, `named_in`, `has_member`, `class_count`). The question "does a scope of the chain
hide this name" no longer unites the sets of the chain: `NameIndex` keeps for each scope the ranges
that its ancestors do not cover, and one binary search in the positions of the name answers it. The
oracle compares all sections with all evidence now, because the sites cite after the symbols as in
Python. Not ported: the script paths (`script_resolution`, `script_evidence`, `_script_alias_bindings`)
belong to PR 4.3a-4 and 4.3a-5; the oracle runs Python without them, so it compares what the
native collector can produce.
