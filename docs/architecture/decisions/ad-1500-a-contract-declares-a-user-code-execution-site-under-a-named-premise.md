# AD-1500 A contract declares a user-code execution site under a named premise

**Status.** Accepted (owner approved the design 2026-11-28; design: `designs/USER-CODE-SITE.md`). Part of #2239. Extends [AD-664](ad-664-a-contract-can-declare-the-reach-of-a-door-site.md), [AD-1052](ad-1052-a-contract-declares-a-trojan-horse-site-by-its-name.md) and [AD-1055](ad-1055-a-premised-pass-reads-pass-under-its-premises.md). Four steps; this record grows with each.

**Reason.** A data generator evaluates user-provided Python by design (`eval` of expressions, `exec` of plugins). The site has no honest finite `loads`. One undeclared site holds every rule that needs a complete graph in every component (`every_module`). `loads: []` would say "this code imports nothing of the product", which is false for user text.

**Decision.**
1. **Step 1: a fact (this record, first part).** The Python collector states, for each `eval` and `exec` site, the names that the call hands to the code it runs: `fresh` (a dict display or `dict(...)`), `shared` (`globals()`, `locals()`, `vars()`, `__dict__`, a `sys.modules` entry), `default` (no mapping: the caller's names) or `unknown`. The fact is on the gap (`GapData.namespace`), not on the wire; the committed facts schema does not change. No rule reads it yet: no verdict changes in this step.
2. **Step 2 (next PR): the contract form.** `user_code: true` on a `trojan_horse_reach` record, with the premise `user_code_outside_product`.
3. **Step 3: the model rule.** Refusals for a shared or default namespace and for an import-system write in the module of the site; the words "PASS under user-code premise <id>".
4. **Step 4: fixtures** for the five counter-probes and the CE measurement.

**Not decided here.** A rule that cannot reach the site is decided but reads "PASS under user-code premise" (a FAIL stays a FAIL). The stated effect is not narrowed to the modules that reach the site.

**Tests.** `native/python/src/survey/hazards_namespace_tests.rs` (each class, `compile` and other sites state none).
