# AD-738 One data file owns the source suffixes of both languages

**Status.** Accepted. Part of #880 and #1390; owner-approved 2026-11-17. Done in #1452.

**Context.** The same source suffixes were written twice, in Rust and in Python:
`SOURCE_SUFFIXES` in `native/contract/src/paths.rs` (a UML target path must end in a source
suffix) and `_CODE` in the shell (`init` detects a TypeScript project by its files). The contract
crate must not depend on `archkeel-facts` (AD-359), so no Rust crate could own the table for the
shell too. A new suffix added to one table and not to the other would make `init` and the contract
disagree about what a source file is. The clone gate skips tables of literals, so only the table
overlap test (`tests/test_table_overlap.py`) showed the pair.

**Decision.** The file `schema/archkeel-source-suffixes.txt` owns the table. Each row is one
`language suffix` pair (`python .py`, `dart .dart`, `typescript .ts`, and so on). The contract crate
embeds the file with `include_str!`. The shell reads it through `core_schema.schema_file`, the same
lookup that finds the frame schema in the wheel and in a checkout. No second table of these names
exists in code: a table of five names or more that overlaps another one fails the table overlap
test.

**Consequences.**
- A new language or suffix is one new row. Both readers see it at once.
- The shell reads one more file at run time, only when `init` looks for TypeScript code.
- The wheel and the sdist ship the file with the other schema files (the `schema/` directory is
  mapped into the wheel).
- The TypeScript collector keeps its own suffix handling (`Suffix` enum in
  `native/typescript/src/source_input.rs`); that is a decision about how to read a file and not a
  table of names.

**Undo.** Put the rows back as a `const` table in `paths.rs` and a tuple in `init_areas.py`, delete
the file, and add the pair to `tests/table_overlap_expected.json` with an issue. The shell then
needs no `schema_file` import (`SHELL-INIT` requires `schema` only for this file).

**Tests.** `test_the_source_suffixes_have_one_owner_that_the_shell_and_the_core_read` (shell reads the
file); `tests/test_table_overlap.py` (no second table); the contract crate tests accept each suffix
of the file as a module target.
