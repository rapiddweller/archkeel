# Typed contract rule grammar — issue #542

The rule grammar will use the existing `ArchitectureRuleKind` and `DecisionMaker` owners
from the graph increment. No second vocabulary or global record-kind inventory is added.
The implementation starts from the verified graph and contract-version carrier
`5933ffbbfd588ac96e36748de937cb1f6e739655`; the shared owners remain unchanged.

## Intended responsibilities

- Architecture graph owns shared rule kinds and decision makers. Model rule variants retain
  their fixed discriminants as `Literal[ArchitectureRuleKind.MEMBER]`; contract attribution
  positions use `DecisionMaker`.
- Model owns compatibility lifetime and the cycle-level grammar used by its contract API.
  The default component cycle level remains absent on the canonical wire.
- Contract codec validates arbitrary JSON and decodes each closed control tag once before
  typed dispatch. Existing bytes, schema feature gates, accepted forms and error messages
  remain stable. Version ownership belongs to the separate contract-version increment.
- Boundary annotation text is an open grammar, not a closed enum of Python type names.
  Existing special bare/native shapes are recognized by exact grammar rules. JSON field
  names, module selectors, paths and freeform amendment authors remain data.

## Execution and evidence

1. Commit this plan before product code; add tests of the nominal decoded objects and
   existing bytes/errors, plus an independently authored native Target for actual rule API
   fields. Run RED in hosted GitHub Actions against the real source, including a fixed
   Target type-weakening control.
2. Convert the rule APIs, decoder dispatch, lifetime and cycle-level ingress. Update only
   real typed consumers required by strict checking. Preserve the graph owners and the
   separate version changes when integrating.
3. Run focused contract/selector/boundary and native tests, Ruff, strict mypy and hygiene.
   Check the actual codec module after the version union. Function selectors do not prove
   module coverage and are not used. Do not claim all of model.py is protected.
4. Run fresh own validation and a normal amendment against the exact final predecessor.
   Do not increase any ratchet or add allowances. Tighten a budget only from measured
   evidence. Keep auxiliary workflows out of the product branch.
5. Open one independent PR, Part of #542, with bounded responsibility and line-cost
   rationale. Parent requests independent Astra review and handles merging.

Avoid a parser framework, mirrored JSON key enums, generic projection wrappers, casts and
string constants used to disguise closed decision tags. Mechanical repetition is acceptable
when it preserves direct evidence and the knowledge rule has one owner.
