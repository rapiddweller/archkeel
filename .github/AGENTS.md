# GitHub Actions

Keep the seven reviewed workflow files. A job has no condition that can skip it;
only an aggregate uses `if: always()`. Do not add temporary or diagnostic workflows;
use existing Make targets or dispatch Full verification. New workflow files require
an explicit change to the inventory in `tests/test_make_gate.py`.

Run `make prune-workflows` to review obsolete workflow registrations against live
Main. Trusted Main maintenance may use `DISABLE=true`; it disables registrations
and preserves run history. Never edit the two initial-PR receipt workflows without
reviewing their pinned trust-boundary digests.

A new workflow file runs on a PR only after it is on Main: the nightly prune disables
registrations whose file Main does not have. Add a PR trigger to an existing Main workflow instead.
