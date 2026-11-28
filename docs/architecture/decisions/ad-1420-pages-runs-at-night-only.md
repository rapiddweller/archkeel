# AD-1420: Pages runs at night only

Status: accepted. Owner approval 2026-11-28. Amends item 3 of AD-1223.

## Why

`pages.yml` started on each push to `main` that changed a gallery input. That was about 17 runs a day.
Each run took 9 to 13 minutes of a runner (545 to 668 s for the gallery step, measured on 2026-11-28,
AD-1400), and nearly every merge changes a gallery input. The page does not need to follow each merge.

## Decision

1. The workflow starts on the nightly `schedule` (03:47 UTC) and on `workflow_dispatch`. The `push`
   trigger and its `paths` filter are removed.
2. Nothing else in the workflow changes: the concurrency group, the permissions and the two jobs stay.
3. The README badge and the published self report can be up to one day old. A person who needs the
   current page runs the workflow by hand.

## Expected saving

About 17 runs a day, each of 10 to 13 minutes: about 3 hours of runner time a day.

## Checks

No test asserts the trigger. The next scheduled run shows the result.
