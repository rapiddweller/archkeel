# GitHub Actions

Keep the five reviewed workflow files. Do not add temporary or diagnostic workflows;
use existing Make targets or dispatch Full verification. New workflow files require
an explicit change to the inventory in `tests/test_make_gate.py`.

Run `make prune-workflows` to review obsolete workflow registrations against live
Main. Trusted Main maintenance may use `DISABLE=true`; it disables registrations
and preserves run history. Never edit the two initial-PR receipt workflows without
reviewing their pinned trust-boundary digests.
