# AD-35 Every review claim is counted on the run result, so the terminal and the JSON name what the page shows

`ir.decisions` derives one count set from the observation, the four [AD-26](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md) and
[AD-33](ad-33-a-components-inside-is-a-level-not-a-list-of-pairs.md) claims together, and `report` and `validate` carry it on `RunResult` beside `agent_decisions`
and `open_decisions`, which are already derived counts rather than evidence. The terminal prints one
line of counts, the HTML keeps its tables, and the result JSON gains the same counts, so an agent
reading the result sees a claim without parsing `architecture.json`. A claim stays a claim: no
verdict row, no exit code, no gate ([AD-26](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md)). Reason: Archkeel named
`archkeel.check.expectation.load_expectation` unreferenced in its own report, and it was acted on
only after a hand-written script recomputed what the page already displayed; `validate` writes no
HTML at all, so there a claim had no surface whatsoever, and `report` shows it only to whoever opens
the file. Two cheaper ways were rejected. Carrying the observation itself on the result reads well
until `codec.result_payload` serializes `observation` whenever it is set, which grows
`archkeel report --json` from a few hundred bytes to the whole artifact. Printing the claim tables
in the terminal buries the three verdicts the command exists to deliver under four tables of
candidates. Limit: counts only, so the terminal never names a symbol; a named list reads like a
worklist, and the detail belongs where the evidence is. Consumers of the result JSON see one new
field, which no schema version announces because the result payload carries none. Check:
`archkeel report` on Archkeel prints 1 unreferenced, 3 oversized, 0 unread and 0 repeated, the
verdict table and the exit code are unchanged, and `archkeel validate --json` carries the same four
counts.

