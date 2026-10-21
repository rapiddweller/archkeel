# AD-257 Rule-driven fact collection

**Decision.** The Python collector collects a fact family only when the effective
contract declares a rule that uses it. The effective contract is the root contract
plus its mounted inside contracts.

One function, `required_resolution_features(contract, inside_contracts)` in
`ir/collection_features.py`, maps rule kinds to families:

| Family (resolution feature) | Collected records | Rule kinds that use it |
|---|---|---|
| `source_roles` | `source_role` records; references marked `local_source_binding` | `source_ownership`, `catalog_use`, `catalog_argument` (reads write and delete roles) |
| `construct_selectors` | `construct_selector` records; member-write witnesses (kept while `extended_call_bindings` is always collected) | `forbidden_construct` with `selector` |
| `guarded_effect_paths` | `guarded_effect` call data | `forbidden_effect_under_condition` |
| `call_arguments` | call argument facts | `forbidden_call_argument`, `catalog_argument`, `catalog_use` |
| `extended_call_bindings` | stored, constructed, constructor and native bindings; member-write witnesses | `call_owner`, `catalog_*`, `forbidden_effect_under_condition`, selector rules |
| `numeric_operands` | `numeric_operand` records | `bounded_numeric_operand` |

The collector always collects these base facts:
- symbols and imports;
- calls with their targets and canonical bindings;
- bindings and typing signals;
- constructs without selectors;
- unknowns;
- non-local value and attribute references.

The report, UML, claims and inventory digests read the base facts.

**Request and response.** Collection protocol 7.0.0 carries the requested families in
`PythonSettings.features`. A 6.0.0 request still means that every family is collected,
so collectors written for 6.0.0 stay valid. The response declares the collected
families in `capabilities.resolution_features`. That set must equal the request plus
the base features, or the response is a protocol error. Dart and TypeScript settings
are unchanged.

**Correctness.** Evaluation computes the required families minus the declared ones.
If a declared rule needs a family that was not collected, the result is a coverage
failure `rule-family-not-collected`. It is never a PASS, and no rule receipt is issued
for it. This failure is routed like `rule-unsupported-by-profile`, so the exit code
is 2.

Validation keeps checking each collected family completely. A record of a family that
was not declared is rejected.

`validate --against` observes each revision under its own contract, so each side
collects the families its own contract needs. Contract digests that differ already
make the delta UNKNOWN (AD-100).

**Reason.** #646 made every scan pay for evidence that only a few rule kinds use:
- On ArchKeel itself, `architecture.json` grew from about 37 MB to 66 MB, and
  `report` took 180 s and 2.3 GB of memory.
- PR CI shards ran past 15 minutes instead of under 9.
- On DATAMIMIC EE (internal), `report` slowed from 77 s to 172 s.

Neither contract declares any of these rule kinds. The gated families make up about
53% of the bytes and 51% of the records.

**Check.**
- Without the rule, a scan contains no records of the gated families, and
  `resolution_features` does not list them.
- With the rule, the existing policy tests pass unchanged.
- Facts collected without a family, combined with a contract that adds a rule needing
  it, produce `rule-family-not-collected`, exit 2, no receipt and no violations.
- A response whose features differ from the request is a protocol error.
- On ArchKeel and EE, the report keeps its rule results and returns close to the
  pre-#646 size and run time.
- PR CI shards stay under 10 minutes.

**Note.** The unreferenced-symbol claim counts references. Without `source_roles`, it
returns to the pre-#646 counting, which did not include local reads.
