# AD-520 A Python import call is an edge of the code but not a statement of a UML target

**Status.** Proposed. Part of #880. It closes the one accepted difference of AD-494 and AD-472
where the core gave PASS and release 4.0.1 gave FAIL. It stays consistent with AD-514.

**Reason.** `importlib.import_module("app.b.t")` and `__import__("app.b.t")` with a plain string
literal are a proven edge since AD-472: the core gives FAIL for the edge under a closed scope that
does not list it (4.0.1: PASS, it never sees the call), and that is kept. But a UML target that
declares the edge `one -> t` was PASS in the core and FAIL in 4.0.1. The UML model of 4.0.1 holds
import statements only; a declared edge is a declared statement. The owner decision: never PASS
where 4.0.1 gives FAIL.

**Decision.**
1. A literal import call is a call-form import. The survey writes it as an `ImportFact` of kind
   `dynamic_import` (the kind that TypeScript uses for `import("m")`), not `import`. The model reads
   the kind as `Import::call_form()`. A UML target does not count every call-form import: it does
   not count a call that names its module with no specifier. `Import::call_by_name()` is that
   fact: kind `dynamic_import` and no `specifier` in the record. The Python survey writes no
   specifier (the store checks it, `store/src/python.rs`); TypeScript writes the specifier of
   each `import("m")` record. No schema field is added: the facts schema is published and does not
   change without a new protocol (AD-345). The model names no language.
2. A declared UML edge `imports(a, b)` is met by an import statement or a call with a specifier.
   When the only edge `a -> b` is a call that names its module (`call_by_name`), the row is FAIL (not PASS) with the cause "declared import is
   only a call-form import": the edge is real and the declaration says a statement. An incomplete
   inventory keeps UNKNOWN, as for an absent edge.
3. The call stays an edge for each other reader: a closed UML scope lists it, `forbidden_dependency`,
   `complete_requires` and the cycle rules see it (stricter than 4.0.1, as before).
4. A call that the survey does not prove stays a `dynamic_import` gap (AD-472, unchanged): an
   aliased `importlib`, `from importlib import import_module`, a variable, f-string or
   concatenated argument, a relative name, a `package` argument, a keyword, a rebound `importlib`,
   a shadowed `__import__`, a `getattr` or stored callee, a module that names `globals()`. The
   run is UNKNOWN.
5. Consistency with AD-514: a call-form import proves no use of a `public` entry, so it gives
   `interface.usage_unknown`; a call that names its module proves no declared statement, so it gives
   FAIL. An import in type position with no bound name (`import("m").T`, `typeof import("m")`) also
   proves no use; `Import::unbound_type()` (kind `import_type` and no binding) keeps its gap, as the
   shape guess did before. `interface` hygiene reads `call_form()` and `unbound_type()`.
   Before this change `call_form` was a guess (no binding, not at module level) that also matched a
   Rust `use`; it is now the record kind.

**Why the two languages differ.** Release 4.0.1 reads the import statements of Python only: a Python
call never reaches its UML model, so a declared edge met only by a call is FAIL there. 4.0.1 reads
TypeScript with a program model in which a lazy `import("../b/t")` is a counted import, so the same
declared edge is PASS there, and the core keeps PASS. A Dart deferred import and a Rust `use` are
`import` records and are not changed. The measure is release 4.0.1 on the review plants: every TypeScript, Dart and Rust row equals `main`.

**Where the core and 4.0.1 differ after this change.** A call-form edge under a closed UML scope:
core FAIL, 4.0.1 PASS (true edge, kept). Each other row of the table below is equal or stricter.

**Tests.** `tests/test_cli_python_literal_call.py` runs 16 forms through the release core against
the UML row of 4.0.1 (`tests/python_literal_forms.py`: all FAIL in 4.0.1; core FAIL for the 3
proven forms, UNKNOWN for the 13 others). `tests/test_cli_core_uml_review.py` `r1` is no longer a
ruled difference.
