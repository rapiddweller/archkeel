# AD-1480 A trojan horse declaration is anchored by its scope, and the line is a hint

**Status.** Accepted. Fixes #2246. Amends AD-664 and AD-1052. Measured by lane L2 in the EE ZERO package.

**Reason.** A declaration named its site by name, line and scope. Any edit above the site moved the line. The
declaration then matched nothing and the site stayed undeclared, which holds every rule: EE went from 24 to 223
UNKNOWN after 7 sites moved. A consumer had to write its records again on almost every commit.

**Decision.** No new contract key and no new schema version.
1. A record with a `scope` is anchored by the module, the form or `name`, and the scope. If the scope holds
   exactly `count` such sites (one by default), they are the sites, whatever their lines are. The `line` is a hint.
2. If the scope holds more sites than `count`, the `line` picks among them. If the line does not pick exactly
   `count`, the record is `trojan_horse_reach.ambiguous`.
3. If the scope holds fewer sites than `count` (a site moved to another function or class, or was deleted), the
   record is `trojan_horse_reach.unmatched`. Its row lists the sites of the module with that name: line and scope.
4. A record without a `scope` keeps the old rule: the `line`, if given, must equal the line of the site.
5. Nothing else changes: `loads`, `changes`, `covers`, the binding check and the premise are as before.

**Counter-examples (each is a plant in `tests/test_cli_python_trojan_horse_name.py`).**
- An edit above a module-level site: applies with the scope, and does not apply without it.
- A site that moved into a function: unmatched, never PASS, the row names `scope build`.
- Two identical sites in one function: `count: 2` applies; a third site gives `ambiguous`; one site gives `unmatched`.
- The declared site is deleted and the same text appears in another function: unmatched.
- A stale line with two sites in the scope and no `count`: `ambiguous`.

**Limit.** The anchor cannot tell the declared statement from a new statement of the same name in the same scope when
the number of such sites is unchanged (one deleted, one added in that function). The collector gives no text or hash
of the statement. The review of the diff of the function shows it. A statement hash needs a facts change (not done).

**Tests.** `native/eval/src/trojan_horse_reach_tests.rs` (three tests; a mutation that ignores the scope fails two),
`tests/test_cli_python_trojan_horse_name.py` (four plants through the release core).
