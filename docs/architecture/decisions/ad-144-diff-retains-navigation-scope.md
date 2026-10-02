# AD-144 Diff retains navigation scope

Diff previously had only global categories, so nested view switches lost their scope.
Diff now groups the same recorded findings by module and declared package scope.
Evidence files, qualified subjects and explicit module fields bind each finding;
unattributable limits remain available at the root. No observation or verdict changes.

An empty scope says no differences are recorded; missing evidence remains UNKNOWN.
A missing or ambiguous counterpart retains its original location and offers an
explicit nearest-scope action. Switching back restores the original view.
Canonical mounted declaration IDs recover the logical Target route after drilling
and returning; multiple exact owners remain ambiguous.
Drill history captures the original route before subject changes; inspecting a
Diff category retains it. Exact declared modules keep their source-file identity.

`tests/test_diff_scope_acceptance.py` covers a CE-sized recursive tree at desktop
and mobile widths; `make report-browser` retains the existing navigation controls.
