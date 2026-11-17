# AD-739: The scope proof reads its causes in one ordered list

Status: accepted (owner order, #1451 Wave 5, F9). Structural: no verdict and no reason text changes.
Part of #880.

`Scope::complete` (the proof of one rule) and `Scope::run` (the proof of the whole run) each walked
their own list of the sources of doubt: the scope state, a profile limit, a gap that states its effect,
a kept pair gap, the gaps that the drop rule drops, a dynamic import and the receipt of the rule. The
two lists were written twice, with their own order, and the order decides which cause a UNKNOWN names.

`scope_order.rs` states each order once, as data:

- `RULE_ORDER`: foreign rule, interface receipt, state, profile limit, scoped gaps, pair gaps, dynamic
  import, receipt.
- `RUN_ORDER`: state, profile limit, pair gaps, scoped gaps, dropped gaps.

One `read` matches every `Source` with no catch-all arm; each source is one function that reads it for
a rule or for the run. `rule` and `run` walk the list and the first source that holds is the cause. A new
source is added to the enum, to the orders that read it and to one function.

The two orders differ on purpose and keep their readings: a rule reads a gap that states its effect
before a kept pair gap, and the run reads them the other way round. Making them equal would change
which cause a frame names, so it is a separate decision. A test pins the order of each subject.

`scope.rs` keeps the brand and the proof; `scope_receipt.rs` holds what the proof reads about a rule
(the receipt, the undecided positions, a dynamic import, the rescued reason, the gap scope and the
scan proof). The split keeps the module graph without a cycle.

Proof of no change: the frame, status and exit code of 25 runs are byte-identical before and after on the
same tree (the 22 runs of `fixtures/matrix.json` run from the gallery, the system report, the shell
and the native self-check), with the engine digest, the snapshot head, the dirty flag and the core path
removed; the model tests (117) pass.
