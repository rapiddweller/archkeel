# AD-520 The Python collector writes the symbol sites that its scopes prove

**Status.** Proposed. Part of #880. It extends AD-518 and AD-512. PR 3 of 5 (L-173).

**Reason.** After AD-518 the Python reply states declarations and no site, so each relationship of
a UML target is UNKNOWN. H-uml lists seven: `inherits`, `realizes`, two `calls`, `references`,
`creates`, `instance_of`. Python resolves a name when the code runs, in the scopes of the use. A
scope below the module that binds the name hides the module symbol, and a name that is written
twice has no one result. PR #1166 found both on TypeScript; they are rules here from the start.

**Decision.**
1. The reply declares `calls` and `references` besides `symbols` (store: five sections).
   `Profile::symbol_sites` is true for Python. A class record has `base_declarations`.
2. **Hidden names.** `survey/bound.rs` stays the one function of "the names that a scope binds".
   A new `hidden(scope chain)` joins it with the parameter names of the function, of each lambda
   and of each def inside it. A name in `hidden` of any function scope from the use to the module
   never resolves to a module symbol. A method does not see its class body; a class body sees
   itself first. A comprehension target, walrus, pattern, `for`, `with`, `except`, import,
   nested `def`, `del` and `global` hide, as the binders already read them.
3. **Written once.** `survey/writes.rs` stays the one reader of writes. A result binding exists
   only for `name = call()` that `Bound::sole` proves in its function and that no parameter
   shares. A name written twice, a tuple target, an attribute or subscript target, `with`, `for`,
   a walrus and `global` give no binding.
4. **Callee.** A call is resolved only when its callee is a plain name that is not hidden and
   names, at module scope, the one sole-bound symbol with a record (AD-518) of this module, or the
   name of an import that is the sole binder (`survey.sole_binders`) of a symbol with a record
   in the target module. Everything else is an unresolved site with no target: `self.m()`,
   `obj.m()`, `super()`, `f()()`, `getattr`, an alias (`h = helper`), a decorated or conditional
   target, a module path, a name from a star import. A receiver whose type is not proven gives an
   unresolved `calls` site; PR 3 proves none.
5. **Construction.** A call that resolves to a class gives `construction`, `creates` and, for a
   proven result binding, `instance_of`. A class with `__new__` in its body or in a local base,
   or an unproven base, makes it `partial`. `x = A()` writes a binding with the text `A()`; a call
   with arguments has no text (AD-518 text rule), so it has no binding.
6. **Bases.** Each base of a class with a record is one declaration: `inherits`, or `realizes`
   when it resolves to a local protocol and the class is no protocol (4.0.1). A builtin,
   `typing.Protocol` or `enum` base resolves to its qualified name. The list is exactly the class
   statement, so a missing wanted base is a true FAIL (`bases_complete`, AD-512).
7. **References.** A name in an annotation of a def resolves in the scope that holds the def
   (module or class body), not in the function. A name that is read as a value in a function
   body resolves by rule 2. Use `type` for the first, `value` for the second.
8. **Module values.** `NAME = <constant>` that one plain statement binds writes a
   `static_constant`; `X: TypeAlias = <name>` with `TypeAlias` from one plain `typing` import
   writes a `type_alias` with the alias text (4.0.1 admits these two; any other value: none).

**Plants** (`tests/test_cli_python_sites.py`, pinned against 4.0.1, truth PASS or DIFF each): a
callee hidden by a parameter, local, `for`, `with`, walrus, comprehension, lambda parameter,
nested def, `except`, `match`, local import, `global`, `del`; a second binder of the module
symbol; `self.m()`, `cls.m()`, `super().m()`, an alias, `f()()`, `getattr`; a result written
twice, in a tuple, with `with`, by a walrus, through `global`, in a conditional expression; a
class with `__new__`; a base through an alias, a conditional base, `Generic[T]`; an annotation
name hidden by a class attribute; a closed scope with an unlisted resolved site.

**H-uml.** Rule 6 gives `inherits`, `realizes`; 4 gives both `calls`; 7 gives `references`; 5
gives `creates` and, with 3, `instance_of` (`item = Unit()`); 8 gives `Text`, `VERSION`. Of 20
entities 19 PASS and 1 is UNKNOWN (`_token`: a bare annotation binds nothing, AD-518 rule 3); of
8 relationships 8 PASS. The row stays UNKNOWN (exit 2), so `fixtures/matrix.json` does not move.

**Rejected.** A receiver-type proof (PR 4). A name resolved through a string annotation. A site
for a function without a record: the model reads it as absent.
