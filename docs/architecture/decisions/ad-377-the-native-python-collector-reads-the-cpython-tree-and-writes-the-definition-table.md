# AD-377 The native Python collector reads the CPython tree and writes the definition table

**Status.** Accepted. PR 5 slice 2a of issue #880. It extends the closed list of AD-367.

**Measurement.** `symbols.py` (1 397 lines) needs 2 113 lines of `source.py` and two inputs from
other modules (`resolve_reexports`, `explicit_factory_unsafe_providers`). Its order follows
`ast.walk`, and 11 modules write text with `annotation_text` (`ast.unparse`). So the base comes
first: the CPython view of the tree, the text of an expression, and the definition table.

**Decision.**
1. **CPython view** (`pyast/`). `Node` gives the class name and `ast.iter_child_nodes` in the
   order of `_fields`: `type_params` from 3.12, `default_value` from 3.13, `TemplateStr` and
   `Interpolation` on 3.14. An `elif` is an `If` in `orelse`, a context or an operator is a
   node, and an f-string has the joined `Constant` values of CPython. `walk` has no recursion.
2. **Text** (`unparse/`). `_Unparser` of 3.11 (fields avoid backslashes) and of 3.12 to 3.14,
   with `_Precedence`. `repr` of a `str` uses the Unicode 14 table of `archkeel-facts`
   (`pyrepr::escapes`, a new public function) and `printable.txt`, the code points that each
   later Python prints. An `int` over 4 300 digits is `ValueError` (`annotation_text` is `None`).
   A t-string field writes `Interpolation.str`, its source text.
3. **Definition table** (`symbols/`). One record for each class, function and method of
   `definition_sites`, with the fields that the module itself decides (`DECIDED` in the test):
   the header, the contexts, the signature, `parameters_contained`, `stored_field_writes`,
   `shape`, the class bases as text, the fields, the attribute declarations, the members, the
   member writes and their scope evidence, `generic_bases` and `guard_boolean_members`.
4. **Not in the reply.** Only the test dump writes the table (`--dump-symbols`, `--dump-texts`),
   and the modules build only in tests and with the feature `dump`. The reply keeps `imports`
   and `unknowns`; the codec and the store refuse 10.0.0 (AD-334 point 8).
5. **Left for the next slices.** The binding proofs (`source_binding_*`,
   `source_member_*`, `signature_decorators_proven`, the overloads), the method decorator data,
   the class kinds and headers (`class_kind`, `class_header_static`, `class_body_control_flow`,
   `base_roots`, `base_declarations`, `member_inventories`, `enum_members`, `frozen_object`,
   `default_instance_result`, `generic_parameters`, `property_members`, the header proofs),
   `annotation_binding_uncertainties`, and the value records (`static_constant`,
   `dynamic_binding`, `type_alias`): their admission reads provider-proven expressions.

**Stricter (AD-367, closed list).**
13. **Depth.** Over `MAX_DEPTH` = 100 nested expression levels the text is `Deep`. The module
    gets a gap "Symbols unseen: <file>: an expression nests deeper than 100 levels" and no record.
    CPython raises `RecursionError` from 158 levels (a dict) to 317 (a `+` chain), measured on
    3.11 to 3.14; the Python collector does not catch it and stops without a verdict (L-20).
    Real code: at most 59 levels (pydantic), 22 (`src/`).
14. **Surrogate.** Ruff reads a lone surrogate escape (`'\ud800'`) as U+FFFD, so native cannot
    write the CPython value. The module gets a gap that names it; Python writes a record.

**Rejected.** (a) All of `symbols.py` in one slice: 3 400 lines of proofs and two cross-module
inputs are not one review. (b) The code generator of ruff: its quotes and parentheses differ
from `ast.unparse`. (c) A partial `symbols` section in the reply: a declared section is whole.
(d) The typed records of `archkeel-facts` with default values for the fields left: the dump
would show values that nobody computed. (e) One module with the writer and its parts: 750
lines. The parts are `impl` blocks of `Writer`, and two calls are pinned gaps of the self-check.

**Limit.** The walks that look for a receiver alias cost the size of the subtree for each
node, as in Python. A clone of the class-name tables is in `clone_baseline.json` with a reason.

**Tests.** `tests/test_collector_native_python_texts.py` (the walk and each expression of
`src/`, `fixtures/` and the named corpora; 50 probes; the depth; the printable table) and
`tests/test_collector_native_python_symbols.py` (the 12 fixtures, `src/`, the named corpora,
40 probes, both gaps), on 3.11 to 3.14; `pyast_tests.rs`, `unparse_tests.rs`, `literal_tests.rs`,
`symbols_tests.rs`.
