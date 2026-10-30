# GitHub Actions

Keep the five reviewed workflow files. A job has no condition that can skip it;
only an aggregate uses `if: always()`. Do not add temporary or diagnostic workflows;
use existing Make targets or dispatch Full verification. New workflow files require
an explicit change to the inventory in `tests/test_make_gate.py`.
