# AD-414 Python compiler completeness needs condition classes

**Status.** Accepted for #1072 and #880. Extends AD-402. The Python reply stays refused.

**Problem.** A message witness does not establish coverage of a compiler condition.
The remaining 1,077 calls need source reachability proofs and condition families.

**Decision.** Classify every remaining call before adding checks.
Keep source-independent resource failures separate from source syntax conditions.
Do not call an allocation failure unreachable merely because a source probe cannot reproduce it.
Keep undecided classes UNPROVED. The store entry condition remains closed.
Use public CPython sources, repository inputs and generated probes only for committed evidence.

**Rejected.** Counting message matches as complete control-flow proofs, or treating resource failures as syntax errors.

**Limit.** This record does not establish compiler completeness or change a production reply.

**Tests.** `test_collector_native_python_completeness.py` pins all initial class counts.
