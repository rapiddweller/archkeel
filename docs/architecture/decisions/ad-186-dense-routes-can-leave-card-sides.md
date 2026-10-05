# AD-186 Dense routes can leave card sides

Top and bottom ports can force unrelated lines onto the same stretch. The shared
renderer keeps its existing route search. If no clear route is found, it tries
source side ports and an exterior rail beyond occupied routes. This retry rejects
exits and arrivals that already overlap: changing the middle cannot repair them.

Only geometry changes. Graph identities, verdicts and evidence stay unchanged.
Visible lines and hit paths use the same route. No new dependency is needed.

Proof: `test_own_ports_keep_mixed_relationship_routes_separate` checks the own
mixed import/reference scope at two viewport widths. The browser suite also covers
navigation through the dense graph boundary. This is no global routing guarantee.
