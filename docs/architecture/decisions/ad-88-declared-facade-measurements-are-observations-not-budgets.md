# AD-88 Declared facade measurements are observations, not budgets

Derive facade exports, re-exports, local definitions, unused re-exports, consumers
per name and distinct names per component pair from existing declarations, modules,
symbols and imports. Reports show measurements, not barrel completeness or budgets.
[AD-99](ad-99-facade-and-coupling-budgets-are-contract-ceilings.md) later adds validation
ceilings over these values.

Reuse typed facts before choosing limits; another scanner/resolver would compete
with AD-9. Consumers include explicit-name imports, AD-99 re-export chains and
proven stars. Bare module imports prove no exported-name use and remain uncounted.
No new records or fields are needed; old observation schemas remain readable.
Checks: the barrel demo and regenerated D-self facade measurements.
