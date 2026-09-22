# AD-78 Baseline fingerprints keep identity and record direction roles

A baseline fingerprint remains the rule ids plus sorted subjects. It is order-independent and
does not change when directional evidence changes.

Directional violation rows may add sorted `roles` objects with `source` and `target` module
names. One fingerprint may carry several roles; none is discarded. A row without both typed
direction fields omits `roles`. AD-89 raises the writer to schema `1.2.0`; the reader still
accepts schemas `1.0.0` and `1.1.0` and gives 1.0 entries no roles. Roles are not identity, but
they are semantic evidence protected by
[AD-90](ad-90-decision-relevant-evidence-is-never-neutral-metadata.md).

Reason: subjects intentionally do not encode importer/imported direction. Reviewers need that
direction, but putting it into identity would split or rename existing baseline entries.

Rejected: one `source`/`target` pair per fingerprint, because an order-independent fingerprint
can represent multiple directions. Also rejected: directional subjects, because that changes the
baseline identity contract.

Check: `tests/test_baseline.py` covers legacy input, deterministic ordering, multiple interface
directions and construct rows without direction evidence.
