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
