# AD-53 `from pkg import name` follows `pkg/__init__.py`'s own binding before a same-named submodule

`imports.collect_package_bindings` reads every scanned `__init__.py`'s unconditional
top-level statements once, before any module's imports are resolved, and records the names each
package binds to something other than the identically named submodule: a `def`, a `class`, an
assignment, an aliased import, or a `from` import naming anything else. `ImportCollector` now
prefers that binding over the submodule interpretation it used alone before: `from pkg import
name` reads as the name `pkg:name` when `pkg/__init__.py` shadows it this way, and as the module
`pkg.name` otherwise, the way `import pkg.name` already resolves. A
plain `from . import name` is read out of the shadow set on purpose, because that statement binds
the identically named submodule itself; over-correcting it into an attribute would misread the
ordinary submodule re-export idiom as its own shadow. `ANALYZER_VERSION` rises to 0.24.0 ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).
Reason: CPython's `_handle_fromlist` checks `hasattr(pkg, name)` before it ever imports a
submodule of that name (issue #23), so a package that assigns, defines or re-exports a name
shadows its own submodule at runtime; the scanner read only the submodule's existence and got
`interface_boundary`'s subject and `dependency_edges`' target wrong whenever the two collided,
an accident CPython treats as ordinary shadowing. Rejected: resolving this per module instead of
once up front, because a module can import from a package the scanner has not visited yet, and
`collect_package_bindings` already costs the cheapest possible pass, one walk of each
`__init__.py`'s own top-level statements; reusing `symbols`, because it never records a plain
assignment; reusing `bindings`, because it answers a different question, an unused function-scope
local rather than a module-scope shadow; expanding a star import inside `__init__.py` to decide
the names it introduces, because that reaches into a second module's exports for one case the
issue does not ask for. Limit: a `__getattr__` or a star import in `pkg/__init__.py` still makes
every one of its attributes undecidable, and the scan keeps the submodule-if-it-exists reading
for the whole package there, which is `docs/rules.md`'s narrowed #23 blind spot; a name bound
inside `if`/`try` is not seen either, matching `literal_all_exports`. Check:
`tests/test_analyzer.py::test_from_import_binds_the_package_attribute_over_a_same_named_submodule`,
`tests/test_analyzer.py::test_from_import_of_a_re_exported_submodule_still_resolves_to_the_submodule`,
and `fixtures/demo_catalog_interfaces.py`'s
`class-a-interface-boundary-package-attribute-over-submodule` row, where `shop.store`'s own
`sqlite` attribute makes `shop.app`'s crossing an `INTERFACE-BOUNDARY` violation instead of the
`DEP-APP-NO-STORE-SQLITE` forbidden-dependency violation the old resolution produced on the
untouched submodule.
