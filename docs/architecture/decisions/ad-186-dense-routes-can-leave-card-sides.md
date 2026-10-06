# AD-186 Dense routes can leave card sides

Retry blocked routes with source side ports and an exterior rail using the existing
router. Reject overlapping departures and arrivals: changing the middle cannot
repair them. This avoids forcing unrelated connections onto the same stretch.

Visible and hit geometry share the route. Identity, evidence and verdicts stay
unchanged; no dependency is added. Reproduced clear routes do not establish a
global routing guarantee.

[Route proof](../../../tests/test_own_uml_target.py).
