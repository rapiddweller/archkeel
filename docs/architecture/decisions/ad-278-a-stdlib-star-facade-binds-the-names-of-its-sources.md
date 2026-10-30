# AD-278 A stdlib star facade binds the names of its star sources

**Status.** Proposed. The owner approves it.

**Decision.** The provider collector proves `pkg.Name` through star imports (`_provider_star_alias`,
`collect.py`) in these cases.
1. The facade `pkg` is a top-level standard library package. Its body holds only star imports,
   a docstring and an `__all__` built from names, attribute reads, `+`, tuples and lists
   (`star_facade_static`, `source.py`). Python 3.13 `pathlib/__init__.py` has this shape.
2. Every star source is a captured module with one literal, unchanged `__all__` and a static
   identity. One computed or missing `__all__` makes the answer unknown, because that source
   can export the name too.
3. Exactly one star source lists the name in `__all__`. The alias points to that source. A name
   in two sources, or one source starred twice, stays UNKNOWN.
4. The alias carries the file evidence of every star source as support.
5. A facade with a named import, a rebinding, a hook or a call in `__all__` stays UNKNOWN.
6. A package outside the standard library keeps the old rule: one star import, and a body of
   imports and a docstring.
7. A star-only stdlib facade has a known namespace, so it can be the parent of a proven child
   module (`pathlib._local`). The child class then keeps its CLASS receipt.
8. The discovery pass captures the star sources one by one, until every source is captured.
9. Python 3.13 joins the `python-compat` job and the classifiers.

**Reason.** On Python 3.13 `pathlib.Path` comes only from `from ._abc import *` and
`from ._local import *`. The proof of one star could not use it. The receiver and `boundary_types`
proofs of `Path` stayed UNKNOWN on 3.13 for almost every project (#743).

**Rejected.**
- Use the same rule for every package. The 3.13+ layout proofs are limited to the standard
  library since #741, and a wrong proven binding is worse than UNKNOWN.
- Accept a named import in the facade. A later star can rebind the name.
- Accept a star source without `__all__`, if it has only public bindings. No stdlib package
  needs it. Add it when evidence asks for it.
- Read the computed `__all__` of the facade. It only steers `from pkg import *`.

**Limits.**
- A star source with a star import of its own is UNKNOWN.
- Stdlib code is trusted not to patch a module at run time (#746).

**Check.**
- `tests/test_python_provider_sources.py`:
  - `test_star_facade_names_the_one_source_that_exports_the_name`: one star, two stars with
    the name in the first or the second source, a name in both, one source twice, a computed
    or missing `__all__`, a rebinding, a starred source, a named import before or after the
    stars, a hook, a computed facade `__all__`, and an `__all__` with a call.
  - `test_only_a_stdlib_facade_holds_several_captured_stars`: the same two stars under a
    package outside the standard library stay UNKNOWN.
  - `test_actual_pathlib_path_has_a_class_receipt`: on 3.13 the real files give the alias and
    the CLASS receipt of `pathlib._local.Path`.
  - `test_provider_discovery_captures_every_star_source_of_pathlib`: runs on 3.13 only.
- `tests/test_python_stdlib_demo.py`: the demo facade exports `Path`. The verdict is PASS on
  3.11 to 3.14 in a local run. CI runs this file on the interpreters of the full suite only.
- Demo catalog, `fixtures/demo_catalog_types.py`: `class-a-boundary-types-stdlib-path-facade`
  has no route UNKNOWN for a `pathlib.Path` facade. The catalog runs on the default Python,
  so it shows the verdict and not the 3.13 layout. The CI check of the 3.13 layout is
  `test_actual_pathlib_path_has_a_class_receipt` in `make python-compat`.
