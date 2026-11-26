# GitHub Actions

Keep the reviewed workflow inventory in `tests/test_make_gate.py`. A job has no condition that
can skip it; only an aggregate uses `if: always()`. The exceptions are `publish-gallery` (AD-462)
and the rolling main build publisher (AD-824). Do not add temporary or diagnostic workflows;
use existing Make targets or dispatch Full verification. New workflow files require
an explicit change to the inventory in `tests/test_make_gate.py`.

To run a check on a PR, add a trigger to an existing workflow instead of a new workflow file.
The one exception is `pr-gate-rerun.yml` (AD-1061): a label or edit trigger in `pr-gate.yml` makes runs that replace the required `PR gate` check.
