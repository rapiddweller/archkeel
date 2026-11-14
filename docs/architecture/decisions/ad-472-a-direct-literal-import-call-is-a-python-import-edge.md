# AD-472 A direct literal import call is a Python import edge

**Status.** Proposed. Part of #880. It narrows three gaps of AD-450 and reads one more runtime form.

**Decision.**
1. Exactly two call forms are an import record and no hazard:
   - `importlib.import_module("a.b")`, when each binding of `importlib` in the module is a plain
     `import importlib` (no alias, no submodule import, no other binding);
   - `__import__("a.b")`, when the module binds `__import__` nowhere.
   The call has one argument and no keyword: a plain string literal with an absolute dotted name.
   The binding counts are those of `binders.rs`; a star import or a type parameter list makes them
   unknown. A module that names `globals`, `vars` or `locals` proves nothing.
2. Only the callee of that exact call is exempt from the reference rule of AD-450. Each other
   reference to `importlib.import_module` or `__import__` stays a `dynamic_import` gap.
3. `from importlib import import_module` stays a door: its import statement is a reference to it.
   A relative name, a `package` argument, a computed argument, an alias, a value use and `getattr`
   stay gaps.
4. The record has no binding, is not at module level and re-exports nothing. Its target follows
   AD-450: a project module, a standard name or an external package.
5. A `.pyi` stub beside its selected `.py` is no gap. Python imports the `.py`; a gap of that file
   holds the run when it does not read or parse. A stub alone and a compiled module stay gaps.
6. The runtime check reads a requirement of clauses `>=X` and `<X` joined by commas. Poetry writes
   `^3.9` as `>=3.9,<4.0`. Each other clause stays unread, so it gives no PASS.

**Reason.** M-review-workflow loads three backends with literal `import_module` calls, and
K-python-realworld has a stub beside its source module. These forms name one known module.

**Rejected.** Trusting `from importlib import import_module`: the door would need an exemption at
its import statement and at each use. Taking the Alembic `sys.path.append` of K-python-realworld
as harmless: its path is computed (`Path(__file__).resolve().parents[3]`), and an appended entry
can resolve a name that the scan classifies as external. Release 4.0.1 reads no `sys.path` write.

**Limits.** No Python fixture reaches PASS with this change. M-review-workflow is held by two
profile limits of the import survey: its `interface_boundary` rules and the symbol selectors of
its component `entry` (AD-426, `limits.rs`). K-python-realworld keeps its `import_system_change`
gap; without it, its inside `complete_requires` rules still need the mount ownership receipt.

**Tests.** `native/python/src/survey/literal_tests.rs` covers each proven form, each neighbour
form and the callee exemption. `targets_tests.rs` checks the record; `layout_tests.rs` the stub
forms; `native/model/src/observed_tests.rs` the runtime clauses.
`tests/test_cli_native_python_imports.py` runs the forms through the release core.
