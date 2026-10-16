# Pairwise call evidence for declared SPOT owners — issue #542

Base: `5d38b66ade5ce0fa4c3ce2f2523712b7454aa987` (product source exactly `5933ffbbfd588ac96e36748de937cb1f6e739655`). Grammar remains frozen.

The structural shape deliberately drops names and literal values. Five enum normalizers therefore share shape `59e615828c9fc471` (18 nodes), although their existing resolved call targets name different canonical enum declarations. This is evidence for refining an advisory review candidate, not proof about runtime behavior or constructor return types.

1. Preserve Source shape production, hashes, historical facts, SPOT owners and thresholds unchanged. Read only existing observation call records.
2. Add native RED controls before production changes: the same converter and an import alias remain candidates; different canonical owners do not; genuine arithmetic remains a candidate; missing, ambiguous, truncated or incomplete call evidence preserves the original candidate; multiple inside functions choose the first still-compatible function. Remove different records on both sides with the same reduced per-scope count to exercise the global collection completeness check.
3. In IR only, index calls by exact source definition identity, require unique sortable evidence positions and fully resolved single untruncated targets, and compare equally sized call sequences pairwise. Do not refine incomplete observations or record counts. Reuse the existing nominal resolution owner; no new resolver, type-result proof, whitelist, cast or normalization framework.
4. Run the complete duplication tests, strict own report and unchanged native ratchets. Compare actual unresolved/partially-resolved call identities and boundary UNKNOWN IDs to the actual predecessor. Run Ruff, strict mypy and hygiene. No allowances or budget increases.
5. Freeze the small carrier and record exact evidence for independent final Astra review. No grammar expansion in this carrier.

## Prior feasibility evidence

[Read-only run 38961039567](https://github.com/rapiddweller/archkeel/actions/runs/38961039567), unchanged product `5933`: all five normalizers have exactly two resolved single-target, nontruncated call records, exact source-definition IDs and line/column evidence. The setter target is identical, while the enum callee identity differs. Constructor-result status remains partially resolved and is not used to justify the refinement.
