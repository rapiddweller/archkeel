# AD-466 The topology types an import by its target, not by the rule view

**Status.** Proposed. Part of #880. It changes AD-464.

**Decision.**
1. The topology section calls an import `external` when its typed target (`Target::External` or
   `Target::Builtin`) is a library or a platform module. This holds for each profile.
2. Before, the section used the rule view of the model. A profile that reads each target by its module
   (Python and Dart) gives the rules `Resolved::Local` for such a target (AD-450). The section then
   showed `resolved` edges to names that are no listed module, and the shell refused the frame
   (`a module edge names no listed module`).
3. A `resolved` edge ends at a listed module. An `external` edge ends at an outside name. An
   `unresolved` edge keeps its specifier. No edge is dropped.
4. The reason text of the scope uses the singular for a count of one: `1 coverage gap`, `1 import is
   not resolved and no gap names it`. The text has one source, `Reason` in `archkeel-model`.

**Reason.** The rules and the display answer different questions. The rules need the module scope of
a Python target. A reader needs to know if an edge leaves the scanned tree. The shell check is right:
a resolved edge must end at a module that the frame lists.

**Rejected.** A weaker shell check: it would show a false `resolved`. A new resolution name for
Python: `external` already says what the reader needs. A change of the rule view: it changes verdicts.

**Limits.** Edge identities of Python and Dart topology change, because the resolution is part of
the identity. The frames of Rust and TypeScript stay equal in bytes. The rule verdicts do not change.

**Tests.** `tests/test_cli_report_topology_python.py` (the default CLI on a small Python project).
`native/model/src/reason.rs` (`a_count_of_one_has_the_singular_form`). `fixtures/matrix.json` pins
the text `1 coverage gap`.
