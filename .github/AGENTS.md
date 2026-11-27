# GitHub Actions

A job has no condition that
can skip it; only an aggregate uses `if: always()`. The exceptions are `publish-gallery` (AD-462)
and the main build publishers (AD-824, AD-1223). Do not add temporary or diagnostic workflows;
use existing Make targets or dispatch Full verification. A new workflow file needs the owner's
approval in its PR text: no test lists the workflow files (AD-1251).

To run a check on a PR, add a trigger to an existing workflow instead of a new workflow file.
No label or edit trigger may start `pr-gate.yml`: a skipped run replaces the required `PR gate` check (AD-1061).
