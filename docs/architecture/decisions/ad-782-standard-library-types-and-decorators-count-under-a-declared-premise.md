# AD-782 Standard library types and decorators count under a declared premise

**Status.** Accepted. Part of #880, fixes #1538. Uses the premise seam of AD-764. Lead decisions of 2026-11-17 (the board, #1538).

**Context.** A `boundary_types` rule (AD-550) allows a scalar, an enum, a plain literal, `None` and the collections of the language. A type of the standard library such as `pathlib.Path` was a type outside the scan, and a definition with a decorator had no record (AD-518): the decorator can return any object. So the demo `python-stdlib-demo` was UNKNOWN with 5 gaps. Python proves neither: code outside the scan can run `pathlib.Path = dict` before the module, and then the annotation names `dict` (CPython 3.12 plant on the board, #1538).

**Decision.**
1. The contract premise `standard_library_unchanged` (`declarations.premises`, contract 3.17.0) says: code outside the repository leaves the standard library unchanged. It is opt-in. A rule that rests on it reads "PASS assuming outside code leaves the standard library unchanged" in the text, the frame (`premises`, `assuming`) and the report. Without it, each such position is UNKNOWN and the cause names the premise.
2. **Types.** The Python collector states a closed table of standard library types by qualified name: the value types and markers of `survey/standard.rs` (`pathlib.Path` and its siblings, `datetime`, `decimal.Decimal`, `fractions.Fraction`, `uuid.UUID`, `ipaddress`, `re.Pattern`, `re.Match`, `typing.Final`) and the qualified collections of the shape reader. The model resolves a name through the import facts and counts it under the premise only when it is in the table. Every other name of the standard library stays a type outside the scan: a mapping such as `collections.Counter`, `object`, or a bare `Callable` must not become an allowed leaf.
3. **Changes in the repository.** The premise covers code outside the repository only. The collector lists a table name as changed, and the model gives a gap for it, when a file of the repository (inside or outside the scan roots, test files excluded as in AD-770) stores an attribute of that name, stores an attribute with a computed name (`setattr` with a computed name), or stores through a namespace (`vars(x)[k]`, `x.__dict__[k]`, `sys.modules[k]`, `globals()[k]`, a mutating method of one of these, `from sys import modules`) or runs code from a text (`exec`, `eval`, `compile`). The forms that the survey already reads as whole-run gaps (`sys.modules`, `exec`) keep those gaps.
4. **Decorators.** A decorated definition still has no record. The collector states its exposed form for the boundary rule only (`Facts.standard`, never on the wire), reading the decorator by its qualified name from the import facts, from the innermost decorator out:
   - `contextlib.contextmanager`, `contextlib.asynccontextmanager`: the same parameters; the return is the yield type of `Iterator[Y]`, `Generator[Y, ...]` or the async forms. Only on the function itself, with the matching `async`.
   - `functools.cache`, `functools.lru_cache` (bare, or called with literal arguments): the same signature.
   - `property`, `functools.cached_property`: an attribute of the return type, on an instance method of the receiver alone.
   - `staticmethod`, `classmethod`: the method kind.
   - `functools.wraps(original)`: `inspect.signature` follows `original`, so the form counts only when the readable signatures of the wrapper and of `original` (an undecorated function of the same module) are equal. Else the gap says "the wrapper and the wrapped function expose different signatures".
   - `dataclasses.dataclass` on a class without bases: the fields in order and a generated `__init__`. `init=False`, an own `__init__`, `kw_only`, `field(init=False)`, `field(kw_only=True)` and `KW_ONLY` are respected; `ClassVar` is no field; `InitVar` is not modeled. The methods of the body get their own forms.
   - A decorator that the repository may change (rule 3), any other decorator, form or body is unread, and the gap names the reason.
5. Under the premise a form is read like a record: a position that shows a class of the repository that no component declares is a violation, and a dataclass is a class for the leaves that name it.

**Consequences.**
- `python-stdlib-demo` opts in and reads PASS assuming the premise; all 5 former gaps are premised subjects. Without the premise it stays UNKNOWN with the cause that names the premise.
- A repository that uses `vars(...)`, `__dict__` writes, `globals()` or `exec` gets no premised standard type: the stated reason names the store.
- The collections of the shape reader were accepted by name before this record, with no premise and no check for a change in the repository. That stays as it was; issue #1718 tracks it.

**Rejected.** Every name of a standard library module: a broad type would pass as an allowed leaf. A record for each decorated definition: every other rule would read the decorated function as a plain one. Reading `#[pymodule]`-style spellings or decorator names without the import facts: a name is no identity.

**Undo.** Remove `Facts.standard`, `facts/src/standard.rs`, `survey/standard.rs`, `declared/decorated.rs`, `declared/wrapped.rs`, the namespace flag of `class_writes.rs`, and the `Standard`/`Wrapped` branches of the model; `premises.rs::declared` returns nothing again.

**Tests.** `tests/test_cli_boundary_types.py` (the premise, its absence, five scanned rebindings, a repository writer outside the scan roots, `contextmanager`, `wraps` with different signatures); `tests/test_cli_boundary_stdlib_decorators.py` (each decorator with and without the premise, two violations made visible through a modeled form, unmodeled forms, a changed decorator, a namespace store, a broad standard type, and the modeled signatures against CPython 3.12); `fixtures/python-stdlib-demo` in `fixtures/matrix.json`.
