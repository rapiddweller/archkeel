# AD-92 Undecided declared evidence is UNKNOWN by default and measured

Count undecided positions centrally, defaulting new unknown kinds to a positive count. Exclude
duplicate coverage failures, standing call/context/private-access disclaimers and external boundary
types; retain finer profile counts where supplied. Otherwise use positive `undecided` or one.

This scalar supports ratchets and baseline budgets. Legacy payloads read zero.
[AD-124](ad-124-rule-pass-requires-complete-scope-receipt.md) replaces the original aggregate PASS
derivation. Proof: [test_unknown_positions.py](../../../tests/test_unknown_positions.py).

## Alias certainty correction (2.0)

Alias body conclusions require unique and member-static Source bindings, including
actual imports. Unknown sibling aliases cannot establish aggregate map uniqueness,
regardless of union order; exact independent literal evidence remains applicable.
The identical-Source old/new resolver comparison exposes 12 existing UNKNOWN
positions: six Language, two ResolverSettings and four State. The measurement
baseline changes from 53 to 65; unresolved-call budget stays 921. No Source defect
is repaired and no UNKNOWN is resolved by this analyzer confidence correction.

The exact positions are ScanConfig.language at observe_repository, run_check,
run_report and run_validate (config and against_config), Analyzer.__call__.language;
CollectionRequest.resolver at ProcessCollector.collect and SourceCollector.collect;
Summary.decision.state at report_summary, init_summary, check_summary and
print_result. Origins are ir.facts.Language, ir.protocol.ResolverSettings and
render.summary.State, respectively; all are unique with unproven member binding.
