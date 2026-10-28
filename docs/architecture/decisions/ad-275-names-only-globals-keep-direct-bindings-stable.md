# AD-275 A names-only `globals()` keeps the direct bindings of its module stable

**Decision.** This amends AD-273. It replaces the rejected alternative "Treat a read-only
`globals()` as safe" for the binding stability of the module.
1. A `globals()` that only reads names (`reads_only_namespace_names`, AD-273) does not make the
   direct module bindings of its module unstable. The callee `globals` is judged with its call.
   In a comparison the dict (or its keys view) must be the last comparator of `in` or `not in`.
   Python runs `a in b in c` as `b.__contains__(a) and c.__contains__(b)`, so any other operand
   is handed to an object that can replace a binding (Codex on #738; this also closes the AD-273 check).
2. One check, `_namespace_may_rebind` in `source.py`, applies this rule. Its callers are
   `stable_direct_module_bindings` and `static_overload_bindings`. Both ask one question: can a
   visible exposure rebind a module-level name?
3. Every other exposure keeps the bindings unstable as before: `globals()` as a dict, `eval`,
   `exec`, `__builtins__`, frames, `__import__` with import effects, and `locals()` or `vars()`
   at module level, also when the code only reads names.
4. A loader that is not bound once at module level stays unproven: in `try` or `if`, rebound,
   deleted, or rebound through `global`.
5. The other users of `exposes_dynamic_namespace` do not change:
   - `binding_names` and `unique_direct_module_bindings` have no exposure test.
   - `_loader_mutations` (imports.py) already applies the names-only rule (AD-273).
   - `_unproven_class_expressions` and `_class_members_receive_owner` judge class creation and
     the class namespace, not module bindings.
   - `unproven_member_bindings` judges member writes through `__annotations__` and frames.
   - `_provider_identity_static` (collect.py) judges the import-time identity of a provider.
   No measurement needs them. Fail closed: they keep every `globals()` as an exposure.

**Reason.** A names-only read gets string keys. It cannot rebind a name. AD-273 applied this to
the loader mutation check only. The older rule in `_stable_direct_module_bindings` still emptied
every binding of the module. The test of AD-273 said so: an `importlib` alias "keeps its own,
older limit ... which this decision leaves alone."

Measured on DATAMIMIC EE (internal): this limit is the cause of one of five unproven dynamic
import sites. The shape is a lazy package `__init__`: `from importlib import import_module`, a
helper that calls `import_module` with a literal dotted name, a module `__getattr__`, and
`__dir__` that returns `sorted(set(globals()) | set(api.__all__))`. The same shape through the
real collector gives UNKNOWN before and a proven import edge after. EE was not run again.
AD-273 rejected this step because it "is not needed to reach 25 on EE".
This site needs it.

**Rejected.**
- Exempt every `globals()` call: `globals()["importlib"] = x` rebinds the loader.
- Exempt names-only `locals()` and `vars()` too: no measurement needs it, and the names-only rule
  then needs a second list of callees.
- Copy the names-only rule into `source.py`: two definitions drift apart. The check reuses
  `reads_only_namespace_names`.
- Skip every callee of a call, as `_loader_mutations` does: then `vars(x)` at module level,
  which only its callee `vars` reports, becomes stable.
- Also exempt the users in rule 5: each asks another question, and no site needs it.

**Not changed.** A target that is not a literal stays UNKNOWN. The other open rows of the draft
class table of #735 (relative names, own-module exposure, `try` and rebound loaders, assignment
aliases) are not changed.

**Check.**
- Class table: [python-dynamic-dependencies.md](../python-dynamic-dependencies.md#names-only-globals-in-the-loading-module-ad-275).
- `tests/test_loader_exposure_scope.py`: 9 names-only forms x 4 loader forms in the loading
  module give FAIL with proof, and the EE shape too. 5 unstable loader bindings and 3 module-level
  `locals()` or `vars()` forms stay UNKNOWN. Each of the 43 `READS` forms keeps `importlib` stable
  exactly when it is names-only (13 chained comparisons included). An overload group stays static
  beside `set(globals())` only. 45 tests fail before AD-275; 24 chained-comparison tests fail on 455ebf40.
- 8 faults in `_namespace_may_rebind` are all caught: skip of every callee, no callee mapping,
  every `globals()` exempt, exposure ignored, no scope-node list, no all-node list, import
  effects always on, and the old rule kept in `static_overload_bindings`. 6 faults in the
  comparison rule are caught: the old rule, no last-op check, no last-comparator check, first
  comparator, all ops membership, single comparison only.
- Demo catalog, `_LOADER_VARIANTS` in `fixtures/demo_catalog_dependencies.py`:
  `loader-names-only-globals-in-loader` gives a proven DEP-RENDER-NO-STORE violation (UNKNOWN
  before). The controls `loader-globals-store-in-loader` (`globals()["importlib"] = ...`) and
  `loader-globals-chain-in-loader` (`__name__ in globals() in SINK`) stay UNKNOWN.
