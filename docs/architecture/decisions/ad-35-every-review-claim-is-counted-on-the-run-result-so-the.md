# AD-35 Every review claim is counted on the run result, so the terminal and the JSON name what the page shows

`ir.decisions` derives the four review-claim counts from the observation
([AD-26](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md),
[AD-33](ad-33-a-components-inside-is-a-level-not-a-list-of-pairs.md)). `report` and
`validate` carry them on `RunResult` beside `agent_decisions` and `open_decisions`.
Terminal output adds one line; result JSON adds counts; HTML keeps evidence tables.
Claims add no verdict or exit-code gate.

An unreferenced `archkeel.check.expectation.load_expectation` had been acted on only
after a script recomputed the HTML claim. `validate` had no claim surface.
Carrying the observation on `RunResult` would serialize the whole artifact;
printing tables would bury verdicts. Counts keep details with the evidence and
avoid presenting candidates as a terminal worklist.

Result JSON had no schema version to announce the new field.
Original checks: self `report` showed 1 unreferenced, 3 oversized, 0 unread and
0 repeated; `validate --json` carried the same counts. Verdicts and exit code stayed unchanged.
