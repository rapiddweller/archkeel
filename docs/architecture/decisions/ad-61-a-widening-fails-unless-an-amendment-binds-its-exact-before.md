# AD-61 A widening fails unless an amendment binds its exact before and after digest

`validate --against <ref>` compares the Git revision's contract with the working
contract through pure `ir.widening` derivations. New permissions, dropped restrictions,
relaxed type-checking scope, added public/required entries and component additions
or removals are widenings; modeled reversals are narrowings. Removed restrictive
rules and added `allowed_dependency` rules widen. Rationale and provenance are neutral.
Unmodeled fields or rule kinds fail closed as widening, including `target_symbol`,
`through`, declarations, labels and roles.

With `--baseline`, compare its Git version too: new fingerprints or higher counts
widen; removed/lower counts narrow. `--write-baseline` compares the proposed contents.
[AD-103](ad-103-baseline-and-amendment-paths-are-relative-to-root.md) now rejects baselines
outside the root, superseding the original unchecked-external-file exception.

Widening yields failures and exit 1 unless `--amendment` binds the exact before/after
`InsideContractTree.comparison_digest`, including recursively mounted contracts.
Without insides, this is the canonical contract digest. An absent prior contract
uses a path-bound absent digest (AD-104). Nonempty `decided_by` and `rationale` record
the decision. `--write-amendment` with those fields writes the approval instead.
Unreadable revisions/contracts and missing/malformed amendments exit 2 with
`against.invalid` or `amendment.invalid`; introduction of an absent contract is
handled by AD-104. Validation without `--against` is unchanged.

Issue #11 concerned agents making code pass by widening its target or baseline.
Digest pairs bind approval to one change while explicit findings let reviewers see
what they approve. Unknown narrowing can ask for an unnecessary amendment, but
cannot silently authorize widening. Git signatures add no needed pair identity.
This branch/base question stays outside the M → B → E → H protocol, which already
rejects candidate contract changes.

Limits: cosmetic unmodeled changes still need amendments; renames appear as removal
and addition. An amendment has no expiry and covers the whole exact pair, not
individual findings. Attribution text is not authenticated.

#310 v2 also binds canonical original-before and actual-after baseline policy:
roles, counts and named budgets. Null means no comparison; path-bound absence
differs from an empty file. Rename classification does not alter the original
bound policy. Legacy v1 remains readable for contract-only comparisons. Explicit
stale records fail even without widening; refused rewrites emit no amendment.
PR CI runs `make against` on the pinned event base before the full gate.

Checks: `tests/test_widening.py` covers rule/component directions, neutral text,
unmodeled changes, exact/stale amendments and padded/shrunk debt; the against
catalog covers command verdicts and unchanged validation without comparison.
