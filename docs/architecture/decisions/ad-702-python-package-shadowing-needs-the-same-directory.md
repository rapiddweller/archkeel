# AD-702 Python package shadowing needs the same directory

**Status.** Accepted. Part of #880; closes #1000.

**Reason.** A package wins over a module of the same name in one directory. Across namespace
portions, the order of `sys.path` decides which file Python imports. The scan roots do not prove
that order.

**Decision.** The collector marks a module as shadowed only when the package is in the same
directory. If files in different directories give one module name, the duplicate-module pass
removes both and reports a gap for each. It does not choose a winner from scan-root order.

**Why.** Python 3.12 imports either file when the order of the two namespace portions changes.
Scan-root order is a selection order, not proof of the program's import path.

**Tests.** `a_module_and_package_in_different_roots_are_both_gaps` checks both directory orders.
`a_package_wins_over_a_module_of_the_same_name` checks the same-directory rule.
