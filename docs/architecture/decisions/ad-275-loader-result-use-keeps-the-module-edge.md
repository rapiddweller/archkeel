# AD-275 The use of a loader result never withholds its module edge

**Decision.** This amends AD-240. It is part A of #723.
1. A proven literal loader call (`importlib.import_module`, `__import__`) gives a module edge with
   evidence class FACT. The use of the result does not change this: bind, read a literal member,
   return, `getattr` with a computed name, store, pass on, discard, rebind. The analyzer works like
   this since AD-240: `_DynamicImports.visit_Call` does not read the use. This AD makes it a rule.
2. The members that the code uses stay unknown. The edge has `symbols_known: false`. A rule that
   names a member reads UNKNOWN for the edge: `forbidden_dependency` with `target_symbol`,
   `interface_boundary` with a `module:name` entry, `complete_requires` through a `module:name`
   port. A rule on modules (forbidden, cycle, boundary, external) decides with the edge.
3. The use of the result is never the cause of a `dynamic_import_limit`. A literal call stays
   UNKNOWN only when the edge itself is unproven. The class table is the one list of these causes:
   loader binding, call target, loader mutation or exposure (AD-273), arguments, package, name.
4. The edge goes to the name as written, for a scanned module and for a module outside the scan.
   A package name gives an edge to the package, not to its submodules.

**Reason.** #723 explains the one unproven literal site on DATAMIMIC EE (internal) by the use of
the result: returned, then `getattr` with a computed name limited by `__all__`. A reproduction of
41 classes through the real collector disproves this. That shape gives a FACT edge (row 05 of the
[class table](../python-dynamic-dependencies.md#use-of-the-loader-result-ad-275)). So the EE site
fails one of the conditions in rule 3. Peter's two seeds are not part A: the name comes from
`"app.main:create_app".partition(":")` and is not a literal at the call (row 28). They need
constant folding, part B of #723.

**Rejected.**
- Implement part A of #723 as a code change: the code already keeps the edge. A change adds nothing.
- Prove the used members from `__all__` of the hook: `getattr` can read any name of the target.
  `__all__` limits the hook, not the target module.
- Withhold the edge when the use is dynamic: a cycle or boundary rule then loses a certain edge.

**Limits.** Kept from AD-240 and AD-273. A `sys.modules[...]` assignment before the call is not
detected; the edge stays (row 22). A name that no module has gives an edge that fails at runtime,
as for a static import. Execution order is not proved: a call in a function that never runs still
gives an edge.

**Open: the cause of the EE site.** Each candidate needs its own amendment and its own evidence:
- Rows 15 and 29: a relative literal with `package=__name__` or `__package__`. A fix can resolve
  `__package__` in any module, and `__name__` in a package `__init__`, when the module does not
  bind that name. `__name__` is `__main__` when the module runs as a script.
- Row 30: a names-only `globals()` (for example in `__dir__`) in the loading module. It empties
  `stable_direct_module_bindings`, so a module-level `import importlib` loses proof. AD-273 kept it.
- Row 32: an own-module exposure (`get_type_hints`, `eval`, `exec`, `__annotations__`).
- Rows 25 and 35: `importlib` bound in `try`/`except` or rebound.
- Row 36: an assignment alias `load = importlib.import_module`; it gives no loader call target.
To decide: read the EE site for these five things, report only the class, then amend.

**Check.**
- `tests/test_loader_result_use.py` runs each row of the class table against a forbidden rule,
  with the target outside the scan and scanned. An "Edge" row gives FAIL, a complete receipt and no `dynamic_import_limit`.
  An "UNKNOWN" row gives one `dynamic_import_limit`. Row 24 gives both.
- Rows 03 and 04 against `target_symbol`, a `module:name` interface entry and a `module:name`
  requires port give UNKNOWN. The control, a static `from sample.errors import Hidden`, gives a
  decided result for each rule. These tests must pass `unknown_positions_by_rule(observation)` to
  `rule_assessments`; with `undecided_by_rule={}` a symbol rule reads PASS.
- Faults that must fail a test: a check on the use of the result, `symbols_known: true` on a
  loader edge, a dropped edge when a `dynamic_import_limit` is also present.
- Demo catalog, `fixtures/demo_catalog_dependencies.py` (the `import_module` row in
  `demo_catalog_constructs.py` is a `forbidden_construct` probe and stays):
  (a) a returned result with a computed `getattr` gives a forbidden_dependency FAIL;
  (b) the same against `target_symbol` gives UNKNOWN with `dependency_symbol_limit`;
  (c) a relative literal with `package=__name__` gives UNKNOWN with `dynamic_import_limit` until
  the open amendment changes it.
