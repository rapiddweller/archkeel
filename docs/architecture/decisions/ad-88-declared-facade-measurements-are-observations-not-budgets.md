# AD-88 Declared facade measurements are observations, not budgets

Archkeel derives facade export counts, re-exports, names defined in the facade, unused
re-exports, consumers per exported name and distinct exported names per component pair from the
existing typed `declarations`, `modules`, `symbols` and `imports` facts. The report shows these
values as measurements only. They do not claim that a re-export barrel is complete and they do
not enforce a budget; a later decision may add such contract policy after evidence exists.

Reason: the architecture needs evidence about facade shape and coupling before it can choose a
safe limit. A second scanner or resolver would create a competing answer to the facts AD-9
already records.

Check: a barrel demo asserts the typed derivation, and D-self regenerates and reads Archkeel's
own facade measurements. Consumers count explicit-name and proven star imports only; a bare
module import proves no exported-name use. The old observation schema remains readable because
no new records or fields are required.
