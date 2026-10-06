# AD-119: Index re-exports once per boundary pass

Build re-export origin, alias-chain and ambiguous-binding indexes once per boundary
pass, then reuse them within the symbol loop. Repeated scanning per facade function
made recursive targets exceed the analyzer deadline.

Resolve ownership against the current contract. Never cache permissions across levels
or scans. The deadline, rule semantics and UNKNOWN behavior remain unchanged;
no global cache or timeout option is needed.

[Work-count proof](../../../tests/test_recursive_boundary_index_work.py).
