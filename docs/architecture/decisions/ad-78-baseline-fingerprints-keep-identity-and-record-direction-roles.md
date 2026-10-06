# AD-78 Baseline fingerprints keep identity and record direction roles

Keep baseline fingerprint identity order-independent. Record sorted source/target roles separately
so reviewers can see direction; one fingerprint may have several roles. Rows without typed direction
omit roles. Previously supported schemas remain readable, without inferred roles.

Roles are not identity, but validation uses them, so
[AD-90](ad-90-decision-relevant-evidence-is-never-neutral-metadata.md) protects their changes as
semantic evidence. Proof: [test_baseline.py](../../../tests/test_baseline.py).
