# Python dynamic dependency evidence

Existing dependency rules consume proven literal `importlib.import_module` and
builtin `__import__` calls. Import aliases, keyword `name`, and relative importlib
names with a literal `package` are supported. Python code is parsed, never imported.
The call site and source evidence back each added import fact.
Call IDs distinguish nested calls even when their source evidence spans coincide.

A loader needs a unique stable lexical import/builtin binding. Native member-escape
syntax and lexical binding owners invalidate visibly mutated or escaped loader
objects across the scanned snapshot. A module that exposes its namespace (`eval`, `exec`)
withholds the proof in that module only; a use of `__builtins__` or of `globals()` as a dict
withholds the proof in every module
([AD-273](decisions/ad-273-namespace-exposure-is-local-to-its-module.md)). A `globals()` that
only reads names exposes nothing and keeps the loader binding stable
([AD-275](decisions/ad-275-names-only-globals-keep-direct-bindings-stable.md)). Conditional mutations are conservative;
execution order and arbitrary runtime effects are not proved. Reexported loader
calls remain UNKNOWN without a proven native call target. Bare assignment
aliases are followed only to invalidate proof, not to invent loader calls.

Unknown bindings, concatenated/runtime targets and unresolved package bases produce
`dynamic_import_limit`. Nonempty or unproved builtin `fromlist` preserves a known
base import and adds uncertainty about children. Empty tuple/list or None is safe;
unproved relative builtin levels remain UNKNOWN.

Affected forbidden-dependency, requires, interface, sibling, external and cycle
rules lose their complete evaluator receipt. Existing source selectors, exact
allowances and applicable type-checking exclusions still apply. A witnessed
violation remains FAIL beside this uncertainty. No dynamic-import ban is added.

This does not certify runtime execution, arbitrary Python reflection, function
assignment alias calls or public value binding. Non-Python profiles retain their
existing capabilities. Historical observations remain historical evidence; reading
one does not recollect its source using the new analyzer.

Each edge reuses the native call identity and lexical binding proof. Static and
dynamic imports share the existing import collector; no collector peer imports
another implementation. No contract, IR or SourceFacts protocol format changes.

Proof: [native controls](../../tests/test_dynamic_dependency_policy.py).

## Names-only `globals()` in the loading module (AD-275)

[AD-275](decisions/ad-275-names-only-globals-keep-direct-bindings-stable.md) classifies the
use of a namespace in the module that calls the loader. Each row runs a literal
`"sample.retired.old"` call against a forbidden rule (`tests/test_loader_exposure_scope.py`).
"Edge" is FAIL with a complete receipt. "UNKNOWN" is one `dynamic_import_limit`. The draft
class table of #735 lists this case as row 30; this table resolves it and keeps rows 25 and 35.

| # | Use in the loading module | `importlib` loader, before | After | `__import__` |
|---|---|---|---|---|
| N1 | Names-only: `set`, `frozenset`, `sorted`, `list`, `tuple` or `len` of `globals()` | UNKNOWN | Edge | Edge |
| N2 | Names-only: `.keys()` chain into N1, the last comparator of `in` or `not in` (`x in y in globals()`), or iteration | UNKNOWN | Edge | Edge |
| N3 | Names-only and nested: `sorted(set(globals()) \| set(x))` | UNKNOWN | Edge | Edge |
| N4 | Names-only in a function, for example `__dir__` | UNKNOWN | Edge | Edge |
| D1 | `globals()` as a dict: variable, subscript, `.get`, `.items()`, `.values()`, `dict()`, an argument, `.update`, a store | UNKNOWN | UNKNOWN | UNKNOWN |
| D2 | A shadowed container: `def set`, `set = f`, `import set`, `class list`, a parameter `len`, `builtins.set` | UNKNOWN | UNKNOWN | UNKNOWN |
| D3 | A comparison that hands the dict or view on: `x in globals() in sink`, `globals() in x`, `x < globals()` | UNKNOWN | UNKNOWN | UNKNOWN |
| E1 | `eval`, `exec`, `__annotations__`, `get_type_hints`, `inspect.get_annotations` | UNKNOWN | UNKNOWN | UNKNOWN |
| E2 | `__builtins__`, `f_globals`, `f_locals`, `f_builtins` | UNKNOWN | UNKNOWN | UNKNOWN |
| E3 | `locals()`, `vars()` or `vars(x)` at module level, also names-only | UNKNOWN | UNKNOWN | Edge |
| B1 | N1 to N4 with `import importlib`, `from importlib import import_module`, an alias, a call at module level or in a function | UNKNOWN | Edge | - |
| B2 | N1 with the loader bound in `try` or `if`, rebound, deleted and imported again, or rebound through `global` | UNKNOWN | UNKNOWN | - |

D1, D2, D3 and E2 withhold both loaders in every module (AD-273). Before the fix of D3,
`x in globals() in sink` counted as names-only: `__import__` and the loaders of other modules
kept a false proof. E1 withholds them in its own module.
E3 stays an exposure: at module level `locals()` is the same dict as `globals()`, and
`vars(x)` can return it. `__import__` needs no module binding, so only D1, D2, D3, E1 and E2
withhold it.
