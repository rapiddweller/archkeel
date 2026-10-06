# AD-53 `from pkg import name` follows `pkg/__init__.py`'s own binding before a same-named submodule

Before resolving imports, `collect_package_bindings` reads unconditional top-level
`__init__.py` statements. Definitions, assignments, aliases and re-exports shadow
a same-named submodule. `from pkg import name` then resolves to `pkg:name`, otherwise
`pkg.name`. Plain `from . import name` remains a submodule re-export, not a shadow.

CPython checks package attributes before importing a submodule (issue #23).
Ignoring this misidentified interface subjects and dependency targets.
Collect once before traversal; symbols omit assignments and binding signals describe
function locals. Analyzer version rises to 0.24.0
([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).

Limits: package `__getattr__` and star imports make attributes undecidable; the
original resolver retained submodule-if-present behavior there. Conditional
`if`/`try` bindings are unseen, as with `literal_all_exports`.
Checks: analyzer probes distinguish shadowed attributes from submodule re-exports.
The `class-a-interface-boundary-package-attribute-over-submodule` demo makes
`shop.store.sqlite` an interface violation, replacing the incorrect forbidden
submodule dependency finding.
