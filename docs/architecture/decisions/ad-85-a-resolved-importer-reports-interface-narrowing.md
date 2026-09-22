# AD-85 A resolved importer reports the public-interface narrowing it proves

When a schema 1.1 baseline role disappears, its fingerprint subjects and `source`/`target`
role prove the exact cross-component importer that was removed. If the target component still
lists that module or symbol as `public`, `validate --baseline` suppresses only that matching
`interface.unused` diagnostic and reports the narrowing: remove the now-unreached entry.

The proof is intentionally narrow. A baseline without roles, an unrelated resolved violation,
an intra-component role, or an entry that cannot be reconstructed exactly leaves the normal
diagnostic in place. New public entries and stale baseline entries remain fail-closed.

No lifecycle state is added. Baseline roles are protected before-evidence (AD-90), and the
current observation supplies the after-evidence.

Check: `tests/test_validation.py` and the `validation-baseline-interface-narrowing` demo row.
