# AD-130: Review starts with findings and snapshot evidence

## Decision

Show verdicts, findings and analysis limits before the existing component explorer.
Provide section links and stable record links. A finding link resets local filters
and reveals collapsed ancestors so the referenced evidence is visible.

Each finding exposes all cited excerpts, identifiers, rule rationale and authorship,
with commit, dirty state, source digest and contract binding. Escape repository content.
Use native details and read-only text fields; clipboard failure selects the text.

## Why and limits

Reviewers need to decide and find the source before exploring the whole graph.
Reuse the offline report and existing records; a separate app adds no proven capability.
Actual/Target Diff compares a snapshot with its contract. Check changes use the existing
accepted/candidate delta; unavailable comparison never means no observed changes.

This changes presentation only. JSON, evaluators and verdicts stay unchanged.
It does not prove better human review; the review-task protocol measures that separately.

## Evidence

`tests/test_review_surface.py` checks order, links, snapshot binding, escaping,
all cited evidence and unavailable comparisons. `make report-browser` checks finding
links through hidden records, denied clipboard access and manual copy without JavaScript.
