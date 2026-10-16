# Contract version ownership plan

User-approved expanded #542 includes parser and protocol controls. Execute with Superpowers RED/GREEN, independent final Astra and separate PR.

## Design

Own supported schema identity in a small pure ir.contract_version component. ContractVersion is a StrEnum preserving all ten supported wire spellings. ContractFeature names actual versioned capabilities. One introduction table drives read and write availability; do not repeat version-string sets in codec branches. The model normalizes valid legacy constructor input once; the codec converts malformed input to its existing version error. Model and codec use the same nominal owner.

JSON key identity, supplied selectors, paths and field grammar remain data. This increment does not certify the remaining rule-kind/role/allowance grammar. Graph supplies its shared ArchitectureRuleKind and DecisionMaker owners in a later contract grammar integration.

## Checks

- Historical versions keep exact canonical bytes and reject unsupported/nontext input.
- Legacy valid direct model construction produces actual enum instances.
- Feature availability is monotonic and existing read/write gates share their introduction policy, including 3.6 module-object grants. The pre-existing missing UML writer gate is outside this bounded change.
- Authored native Target binds schema_version and supports parameters/return. Widened source fails against unchanged intent.
- The new pure module has a native whole-module string-control guard; raw equality/membership/match/Final probes fail.
- No higher debt ceilings or allowances. Preserve #544 grants and all current shared migrations.

## Work

- [ ] Hosted RED on unchanged model and parser.
- [ ] Implement nominal version owner and shared feature policy.
- [ ] Replace repeated codec version dispatch and retain all valid legacy encodings.
- [ ] Add named ports, independently authored Target and native mutation tests.
- [ ] Focused compatibility, static checks, real own observation and fresh amendment.
- [ ] Independent Astra review and final combined CI before merge.
