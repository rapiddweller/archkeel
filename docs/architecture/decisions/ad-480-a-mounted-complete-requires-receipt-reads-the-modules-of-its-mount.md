# AD-480 A mounted complete_requires receipt reads the modules of its mount

**Status.** Proposed. Part of #880. It extends AD-384 and AD-385.

**Decision.** The ownership receipt of an inside contract reads the source domain of its mount,
as release 4.0.1 does (`rules.py` `_inside_rule_scope_is_complete`, `rule_evaluation_facts`):

1. The subjects are the modules of the mount: the modules that the parent component claims, of
   the modules that its owner holds (`_inside_source_domain`). A mount without such a module has
   no receipt (`Reason::NoSubjects`).
2. Each subject must have exactly one owner among the components of the inside contract. An
   unowned or a doubly owned module inside the mount keeps the row UNKNOWN.
3. A module outside the mount is not a subject. It does not block the receipt.
4. The scan roots must hold the packages and the exact modules of the inside components, and also
   the packages and the exact modules of the parent component (`source_roots`,
   `source_exact_modules`). Else the row is UNKNOWN.
5. The edges are unchanged: an import counts only when its source is a module of the mount and
   both ends have an inside component (`_requires_import_verdicts`). An edge to a module outside
   the mount is the business of the parent contract.
6. The root model holds every module, so the ownership of a root receipt does not change. The
   `interface_boundary` receipt, root and mounted, needs the same scan check (point 4) and
   ownership proof, as in 4.0.1 (`receipt_scope_complete`). Before, a root interface row had no
   scan check and could PASS where 4.0.1 gives UNKNOWN.

`Scope::complete`, `Scope::pass_run` and `ModelTree::pass_run` stay the only PASS makers. The
model, the evaluator and the report name no language.

**Reason.** Each mounted `complete_requires` row was UNKNOWN: the receipt asked each module of the
whole graph for one owner among the components of the mount. Release 4.0.1 decides these rows.

**Rejected.** Dropping the parent scopes from the scan check: a parent package with no file or an
exact module outside the roots would then give PASS where 4.0.1 gives UNKNOWN.

**Limits.** 4.0.1 accepts an unowned blank Python `__init__.py` inside a mount. The core does not;
it stays UNKNOWN there (stricter). No fixture row of `main` moves: its other mounted rows are
UNKNOWN for other causes. With the Dart wiring (#1148), the five mounted rows of
`fixtures/I-flutter-shop` become PASS, as in 4.0.1.

**Tests.** `tests/test_cli_core_interface_receipt.py` runs the nine interface trees of the
review (seven mounted, two root): each row is UNKNOWN, as in 4.0.1. `receipts_mount_tests.rs`
reads the guards of no subject, an incomplete inventory and a planned component of a mount.
`tests/test_cli_core_mounted_receipt.py` plants seven TypeScript trees with a mount:
PASS, FAIL, an unowned module and a doubly owned module inside the mount, an edge across the mount
boundary, a parent exact module outside the roots and a parent package without a file. Each
expected row is the row of 4.0.1 on the same tree.
