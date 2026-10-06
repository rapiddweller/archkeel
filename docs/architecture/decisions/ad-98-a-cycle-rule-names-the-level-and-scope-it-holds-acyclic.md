# AD-98 A cycle rule names the level and the components it holds acyclic

Cycle rules name component or module level and optional component scope. Report a whole SCC when any
member touches scope, retaining every internal import's evidence. Default fields preserve old bytes;
neither level implies the other.

Only a strict-subset contraction under a current cycle rule can replace known cycle debt without
accepting new debt. Changing level, adding scope or dropping a scoped component widens; removing
scope narrows. Package backing distinguishes import cycles from roll-up without proving every
package participates.

`TYPE_CHECKING` edges still count. Proof:
[test_cycle_levels.py](../../../tests/test_cycle_levels.py).
