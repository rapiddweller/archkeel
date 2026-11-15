# AD-560 A lazy import table bounds the import calls of a module `__getattr__`

**Status.** Proposed. Part of #880. This refines AD-472 and AD-450.

A package `__init__` can import its public names late: a module-level dict maps each name to
`(package, module)`, and a module-level `def __getattr__(name)` calls `import_module` with values
of that table. `pydantic/__init__.py` (v2.14.3) does this. Release 4.0.1 never read these
edges, so its PASS there was unearned. The core gave 145 `dynamic_import: __spec__` gaps and no edge.

**Rule.** All of the following must hold. Each failing part keeps its own gap.

1. *Table.* A name bound once to a dict literal. Keys are string literals. Values are tuples
   whose items are string literals or the package of the file: `__spec__.parent`, `__package__`,
   `__name__` of a package `__init__`. The module must not bind these names (a star import binds
   a name only when the starred module has a literal `__all__` that lists it). Each other use of
   the table name is a read: `.get`, `.items`, `.keys`, `.values`, a subscript load, `in`. No other
   module of the scan contains the table name.
2. *Function.* A plain module-level `def __getattr__(p)` with one parameter, no nested scope, no
   `global`, no `match`. An import call has a proven callee: `from importlib import import_module`
   or plain `import importlib`, each the only binder. Its arguments are literals, f-strings and `+`
   of atoms. An atom is a name whose every binding unpacks a table entry, or iterates the table,
   or the parameter after a guard (`if p not in T` or `if v is None` for `v = T.get(p)`) that
   returns or raises. The parameter alone as the whole module name keeps the gap.
3. *Targets.* The Cartesian product of the value sets of the arguments (at most 4096), each
   candidate resolved as `importlib.util.resolve_name` does, with each package. A candidate that is
   a project module or lies outside the project is an import record. A candidate that no file of
   a regular project package holds (the package module exists and never names `__path__`) is no
   import and no gap. A candidate under a namespace package keeps its `project_module_not_found`
   gap. A candidate that is no dotted name, or a door (`hazards::hazard`), keeps the call gap.
4. *`globals()` writes.* Only `globals()[k] = value`, or the same through a local bound only to
   `globals()`, where `k` is an atom. A table key equal to `import_module`, `importlib`, the table
   name, `globals`, `getattr`, `__getattr__`, `__spec__`, `__package__`, `__name__` or
   `__path__` keeps these gaps.
5. Other calls of the function are judged in their own module as before.

**Why Cartesian.** The survey does not track which entry a name came from. The product is a
superset of the real calls, so an import that Python makes is always an edge. The cost is noise:
for `pydantic` the product holds external names such as `pydantic_core.AfterValidator` and
`__module__`. They are external facts of one package each, not project edges.

**Literal tests.** A test `slot == 'x'` or `slot != 'x'` of an enclosing `if` (body and plain
`else`, the name not bound again inside) keeps only the entries that fit it. A slot is a name
that unpacks the entry `v = table.get(p)` of the guard; the narrowing then also applies to the
requested name and to the other slots of that entry. Any other name only loses or keeps the
literal. For `pydantic` this removes `__module__` and `pydantic_core.<key>`; the product of the
sets of different slots stays (`pydantic_core.aliases`).

**Layout.** The modules of the proof are siblings in `survey`, `lazy_cover` holds the type that
`hazards` reads, and the contract names them for `ruff_python_ast` and `ruff_text_size`.

**Scope.** The exemption covers the callee, its import statement, the `globals` name of a proven
write and the `__spec__.parent` reads of the table. Every other site of the module stays a gap.
`uses.rs` still sees the old sites, so the module keeps its opaque surface (no route through it).

**Measurement.** `pydantic` v2.14.3 (`roots=.`, namespace `pydantic`): 324 -> 174 gaps of the
Python collector outside the 357 non-Python files. The 145 `__spec__` gaps of `pydantic/__init__`
are gone and 174 import records are new. The 5 star import gaps and 1 re-export ambiguity stay.

**Tests.** `survey/lazy_table_tests.rs`: the pydantic shape with `python3.12` as truth (each
requested name: every module that `sys.modules` gains is an edge), the cross-entry plant, and
mutation rows that keep a gap: written table, `.update`, table from a call, non-literal item,
unguarded parameter, the parameter as module name, key `__path__`, a bound `__spec__`, a product
above 4096, another module that names the table, a namespace package, a starred module that
can bind `import_module` or `__spec__`.

**Limit.** A file of a regular package that the scan excludes (test sources) is not seen. A
dropped candidate names no scanned file; the survey does not read the directory.
