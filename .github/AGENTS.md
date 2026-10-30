# GitHub Actions

Keep the four reviewed workflow files. A job has no condition that can skip it;
only an aggregate uses `if: always()`. Do not add temporary or diagnostic workflows;
use existing Make targets or dispatch Full verification. New workflow files require
an explicit change to the inventory in `tests/test_make_gate.py`.

To run a check on a PR, add a trigger to an existing workflow instead of a new workflow file.
