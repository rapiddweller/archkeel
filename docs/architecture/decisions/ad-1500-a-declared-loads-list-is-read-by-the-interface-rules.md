# AD-1500 A declared `loads` list is read by the interface rules

**Status.** Accepted. Fixes #2245. Amends AD-664. Measured by lane L2 in the EE ZERO package.

**Reason.** A `trojan_horse_reach` record with a `loads` list makes one declared import for each loaded
module. The import has no known name. The interface rules judged it as an unread binding, so an honest
declaration kept the rule UNKNOWN. On EE the task registry declares 34 task modules:
`RUNTIME-TASKS-INTERFACE-BOUNDARY` went from PASS to UNKNOWN (357 imports), and `EE-INTERFACE-BOUNDARY`
held 3,086 imports instead of 803.

**Decision.** `interface::assess` judges a declared import on the loaded module, as AD-749 judges a
whole-module import with a stated surface:
1. The owner of the module lists the module in `public`: PASS.
2. The owner lists only `module:name` entries of it: UNKNOWN, named `unread_binding`.
3. Otherwise no name of the module is public: FAIL.

No contract key and no schema version change. A module that the scan does not hold is still
`trojan_horse_reach.invalid` (AD-1052), and the declaration does not apply.

**Counter-examples (plants in `tests/test_cli_python_declared_loads_interface.py`).**
- Two loaded modules, both public: PASS.
- A prefix that covers a module outside the public interface: FAIL, never PASS.
- A module that `public` lists by name only: UNKNOWN.
- A declared module that the scan does not hold: named gap, the rule stays UNKNOWN.

**Limit.** A module that the site loads but the record does not list is outside the declared premise
(AD-664). The record states it as a premise and the row prints it. Not done.

**Tests.** The four plants through the release core.
