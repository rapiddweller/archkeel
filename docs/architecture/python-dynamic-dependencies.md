# Python dynamic dependency evidence

Existing dependency rules consume proven literal `importlib.import_module` and
builtin `__import__` calls. Import aliases, keyword `name`, and relative importlib
names with a literal `package` are supported. Python code is parsed, never imported.
The call site and source evidence back each added import fact.
Call IDs distinguish nested calls even when their source evidence spans coincide.

A loader needs a unique stable lexical import/builtin binding. Native member-escape
syntax and lexical binding owners invalidate visibly mutated or escaped loader
objects across the scanned snapshot. A module that exposes its namespace (`globals()`,
`eval`, `exec`) withholds the proof in that module only; a use of `__builtins__` withholds the
proof of `__import__` in every module
([AD-273](decisions/ad-273-namespace-exposure-is-local-to-its-module.md)). Conditional mutations are conservative;
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

## Use of the loader result (AD-275)

[AD-275](decisions/ad-275-loader-result-use-keeps-the-module-edge.md) keeps the module
edge of a proven loader call, whatever the code does with the result. The table shows
each class with a forbidden rule from `sample.caller` to `sample.retired`. The target is
`"sample.retired.old"`, outside the scan and scanned; both columns give the same result.
"Edge" is a FACT import edge and a complete receipt. "UNKNOWN" is one
`dynamic_import_limit`. AD-275 changes no row; rows marked "open" are candidates for
the cause of the DATAMIMIC EE (internal) site.

| # | Class | Today and after AD-275 | Cause |
|---|---|---|---|
| 01 | Result bound, literal member read | Edge | - |
| 02 | Result unused (side effect only) | Edge | - |
| 03 | Result returned from a function | Edge | - |
| 04 | `getattr(result, name)` with a computed name | Edge | - |
| 05 | Module `__getattr__` limited by `__all__`, computed `getattr` | Edge | - |
| 06-08 | Result stored in a dict, a list or a class attribute | Edge | - |
| 09 | Result passed to an unknown callee | Edge | - |
| 10 | Result name rebound later | Edge | - |
| 11 | Result bound, `getattr(mod, "create_app")` | Edge | - |
| 12 | `from importlib import import_module as load` | Edge | - |
| 13 | Keyword `name=` | Edge | - |
| 14 | Relative literal, literal `package` | Edge | - |
| 17 | Absolute literal with `package=` (Python ignores it) | Edge | - |
| 18 | Literal names a package | Edge to the package | - |
| 22 | `sys.modules[...]` assigned before the call | Edge | Not detected (limit) |
| 23 | `__import__` with a literal | Edge | - |
| 24 | `__import__` with a computed `fromlist` | Edge and UNKNOWN | Children unknown |
| 26, 34 | Loader imported inside the function | Edge | - |
| 27 | Module defines `__getattr__`, call elsewhere | Edge | - |
| 31 | `import importlib.util`, then `importlib.import_module` | Edge | - |
| 15 | Relative literal, `package=__name__` | UNKNOWN (open) | Package not a literal |
| 29 | Relative literal, `package=__package__` | UNKNOWN (open) | Package not a literal |
| 16 | Relative literal without `package` | UNKNOWN | No base |
| 19 | Literal is not a dotted identifier | UNKNOWN | Not a module name |
| 20 | f-string over a module constant | UNKNOWN | Not a literal (#723 part B) |
| 28 | Peter's seed: `"app.main:create_app".partition(":")` | UNKNOWN | Not a literal (#723 part B) |
| 21 | `importlib.import_module = ...` in another module | UNKNOWN | Loader mutated (AD-273) |
| 33 | `globals()[name] = value` in a lazy hook | UNKNOWN | Exposure, every module (AD-273) |
| 32 | `get_type_hints` in the loading module | UNKNOWN (open) | Exposure, own module (AD-273) |
| 30 | `sorted(set(globals()))` in the loading module | UNKNOWN (open) | `importlib` binding not stable |
| 25 | `import importlib` in `try`/`except ImportError` | UNKNOWN (open) | Loader binding uncertain |
| 35 | `importlib` rebound in the module | UNKNOWN (open) | Loader binding not stable |
| 36 | `load = importlib.import_module`, then `load(...)` | UNKNOWN (open) | Assignment alias, no call target |
| 41 | Loader imported from another scanned module | UNKNOWN | Reexported loader |
| 37, 38 | Call with `**kwargs` or `*args` | UNKNOWN | Arguments not proven |
| 39 | `__import__` with `level` 1 | UNKNOWN | Relative builtin level |
| 40 | `__import__` with literal `level` 0 | Edge | - |

Row 30 applies to an `importlib` alias at module level. `__import__` and an import
inside a function keep the edge. Row 33 withholds both loaders in every module, so it
cannot explain one unproven site among proven ones.

A rule that names a member reads UNKNOWN for a loader edge (`symbols_known: false`):
`forbidden_dependency` with `target_symbol`, `interface_boundary` with a `module:name`
entry and `complete_requires` through a `module:name` port. A static `import pkg.mod`
passes a `target_symbol` rule, so there a loader edge is stricter.
