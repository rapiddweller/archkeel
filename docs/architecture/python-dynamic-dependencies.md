# Python dynamic dependency evidence

Existing dependency rules consume proven literal `importlib.import_module` and
builtin `__import__` calls. Import aliases, keyword `name`, and relative importlib
names with a literal `package` are supported. Python code is parsed, never imported.
The call site and source evidence back each added import fact.
Call IDs distinguish nested calls even when their source evidence spans coincide.

A loader needs a unique stable lexical import/builtin binding. Native member-escape
syntax and lexical binding owners invalidate visibly mutated or escaped loader
objects across the scanned snapshot. A module that exposes its namespace (`globals()`,
`eval`, `exec`, `__builtins__`) withholds the proof in that module only
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
