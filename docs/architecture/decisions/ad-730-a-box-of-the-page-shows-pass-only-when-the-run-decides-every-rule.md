# AD-730: A box of the page shows PASS only when the run decides every rule

Status: accepted (lead plan #1451, Wave 1 S1, 2026-11-17). Fixes #1468. Part of #880. Amends AD-606.

1. Problem. AD-606 drew a component, a dependency cell and a level edge of the Explorer as PASS
   when no violated place, no collection gap and no held pair named one of its modules. The status
   of the run was not read. A run can be UNKNOWN for a reason of the whole run: an UNKNOWN rule
   without a gap (for example `unused_public` when the collector does not state every public
   symbol), a refused contract, an unverified producer, an open scope, or a frame without a
   status. Then every box was a green PASS. On main `9d8b37a87` the native self-check was UNKNOWN
   with 97 PASS boxes and 3010 PASS cells. That is a false PASS on the page.
2. Rule. The floor of a run is PASS when the run is PASS, or when the run is FAIL and no rule row
   is UNKNOWN. Else the floor is UNKNOWN. A box, a cell and an edge show the worse of their own
   status (FAIL for a violated place or a failing rule, UNKNOWN for a gap or a held pair) and the
   floor. A rule of the run that is not decided can break inside any box, so no box is proven PASS.
3. A part of a system is a run of its own with its own status and rules (AD-616). A box inside a
   part reads the floor of that part; a box outside every part reads the floor of the system. A
   PASS part stays PASS beside an UNKNOWN part. A part rule that the frame does not state counts as
   UNKNOWN.
4. A box under the floor without a gap of its own says so: "No violated place and no gap inside,
   but the run is not decided: no rule is proven here." The line of the architecture section still
   counts only the boxes that a gap holds.
5. The page reads the run status and each rule verdict as the typed wire form of the frame
   (`Status`, `RuleVerdict` of `head.rs`) and shows a box as one ordered enum (`PASS < UNKNOWN <
   FAIL`; `worse` is `max`). Every match on the new types is exhaustive. A frame without a status
   reads as `None` and its heading stays `Verdict: unavailable`. Such a frame names its cause and
   a next step in NEXT and in Unknown; without a cause the step is
   `Run archkeel validate --verbose`.
6. The JSON frame does not change. The HTML changes only where the floor applies: on the fixtures
   of the repository the status words of boxes, cells and edges of UNKNOWN runs go from PASS to
   UNKNOWN, and the reason sentence of rule 4 is added. PASS runs and runs that already show
   UNKNOWN everywhere are byte-identical except the core digest.

Proof: [html_floor_tests.rs](../../../native/report/src/html_floor_tests.rs),
[html_status.rs](../../../native/report/src/html_status.rs) (one test per transition),
[test_cli_report_page.py](../../../tests/test_cli_report_page.py)
(`test_no_box_cell_or_edge_of_an_unknown_run_shows_pass`).
