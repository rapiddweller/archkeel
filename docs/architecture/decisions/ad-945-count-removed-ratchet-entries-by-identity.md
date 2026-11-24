# AD-945 Count removed ratchet entries by identity

**Decision.** The merge guard counts entries removed from each ratchet file since the merge base.
It compares entry identities and retains repeated entries. New entries do not offset removals.
The existing limit and `ratchet-lead` approval stay unchanged.

Gap identity is its kind, subject and reason. A growth approval uses its `entry`, not its
explanatory reason. A violation uses its rule, source, target and cause, not its issue number.
Rule and unknown maps use their keys. This follows the identities of `native_expected.py`.

**Reason.** A net count permits 100 removed gaps when 100 other gaps are added. The merge guard
must request approval for the removals even when the total size does not change.

**Rejected.** Counting changed lines depends on JSON formatting. Counting net entries hides
replacements. A set loses repeated gaps. None provides the requested removal count.

**Limit.** This guard checks the two existing ratchet files only. It does not decide whether a
removal is correct. The lead still makes that decision.

**Check.** `tests/test_merge_pr.py` checks both ratchet files, replacement, duplicate gaps,
approval, unchanged identities and the 50-entry boundary.

**Superseded in full by [AD-1064](ad-1064-the-pin-files-are-deleted-and-the-base-comparison-is-the-only-self-check-gate.md).**
