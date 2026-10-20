# AD-244: An empty literal `__all__` states an empty surface

A module states its export surface when its `__all__` lists names, or when the analyzer
proved `__all__` is bound once to a literal (AD-99), including `__all__ = []`. A module that
states a surface exposes exactly those names, so an empty literal exposes none. A module
without a proven `__all__` states no surface and keeps the existing fallback: non-underscore
names for component facades (AD-9) and module-only checks for promised names (AD-71).

Before, `all_exports` was empty both for "no `__all__`" and for `__all__ = []`, and every
reader treated empty as "no restriction". A component facade with `__all__ = []` therefore
exposed every public name, and a promised name went unchecked. Both failed open.

`archkeel.ir.model:stated_exports` owns this decision: it returns a module's stated names, or
`None` when it states none. Every module-to-exports map is built from it, and readers test
`is None`, never truthiness.
Facade budgets (AD-88) and the interface profile (AD-99) had kept an empty `__all__` open
only to match that reading; they now count a facade of no names as well.
Submodule imports are unaffected: they target the submodule, not the package's names.
A star import binds exactly the stated surface, so a module entry covers it for any `__all__`.
Compatibility shims still require a non-empty `__all__` (AD-87).

[Facade controls](../../../tests/test_empty_literal_all.py)
