# AD-85 A resolved importer reports the public-interface narrowing it proves

A resolved baseline role can prove which exact cross-component importer disappeared. Suppress only
its matching `interface.unused` finding and report the now-unreached public entry for removal.

No roles, intra-component roles, unrelated resolved violations or unreconstructable entries provide
that exemption. New declarations and stale debt remain fail closed. Protect before-evidence through
[AD-90](ad-90-decision-relevant-evidence-is-never-neutral-metadata.md). Proof:
[test_validation.py](../../../tests/test_validation.py).
