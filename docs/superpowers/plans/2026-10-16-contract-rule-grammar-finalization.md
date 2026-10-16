# Contract rule grammar finalization — issue #542

## Goal and architecture

Finish the bounded nominal contract grammar on babfb45cf15588a7313e3c7ab37a8b256fccecc2. Reuse graph-owned ArchitectureRuleKind and DecisionMaker. A fieldless ArchitectureRuleGrammar mixin owns the two idempotent constructor conversions for twelve model and two graph rule DTOs; frozen/slotted field order stays unchanged. Model retains CompatibilityLifetime and CycleLevel. No generic normalization registry, new resolver authority, Record.kind inventory or JSON-key enum.

Spec: issue #542 and the accepted constructor/API design. Tech stack: Python dataclasses/StrEnum, existing codec, pytest and native Archkeel on GitHub Actions. Remote branch isolation replaces a local worktree; auxiliary workflows are excluded from delivery.

## Global constraints

- Apply only the nine source-file delta from 5933ffbbfd588ac96e36748de937cb1f6e739655 to a0948a708198a0aab432d00017f45f184b0d05d1 using real Git three-way merging onto the current predecessor. Preserve all later diagnostics, version ports, artifact and other stages.
- Keep the two direct re.fullmatch calls prepared in d48e36f623a15734a7569e946646cdeaae030b88. Open annotation syntax, JSON labels, module names and paths stay data.
- Wire bytes, default component-level omission, accepted legacy constructors and existing error semantics remain compatible. Freeform amendment authors and broader assessment attribution remain data.
- No budget increase, allowance or detector exception. No whole-model protection claim. The codec guard covers the actual entire codec only after native proof.

## Review focus

1. All fourteen explicit legacy rule constructors normalize once to the canonical enum identities; enum inputs, dataclasses.replace, positional order, frozen and slots remain valid.
2. Special cycle/lifetime and optional component decision-maker normalization do not broaden their vocabularies.
3. Authored API intent stays independent of implementation: preserve the forty-three field/class Targets and add only narrowly named mixin intent; raw-control and annotation-widening mutations run with fixed contract bytes.
4. Dispatch and version gates preserve real compatibility, including malformed values, default omission and module-path error priority.
5. Actual unresolved and partial call sites include target multiplicities; stable boundary-position identities are compared against the exact predecessor rather than inferred from counts.

## Tasks and ledger

- [x] 1. Commit plan and inventory before implementation. Build tests plus independent authored intent, then watch actual constructor/native RED.
- [ ] 2. Three-way merge only the original grammar delta, resolve current-owner overlaps, add the approved fieldless mixin and direct legacy constructor normalization.
- [ ] 3. Run contract, selector, boundary and native API/guard tests; Ruff, strict mypy and hygiene. Compare complete UNRES/PARTIAL sites and UNKNOWN IDs; preserve/tighten only measured ratchets.
- [ ] 4. Union onto the final parent supplied by Root; generate a fresh normal amendment against that exact commit, then no-write verify unchanged source.
- [ ] 5. Freeze intended source and authored intent separately, report line costs and exact evidence, hand off for independent Astra review before merge.

Pre-flight: model consumes the graph grammar owner; codec consumes those nominal DTOs; native fixtures must copy the real mixin owner. The current model has no separate ContractRuleKind, and reflective RULE_KINDS is the sole remaining get_args/get_type_hints use.
Ruling: use one explicit fieldless owner instead of fourteen repeated normalizers; the existing graph module publication already covers this named API, so do not broaden a module boundary.

Task 1: complete — plan2626c158, tests9741c00a. Hosted RED38971885025/job117211971106:39failed/21passed; twelve model direct positional constructors retain raw kind, optional component decision retains raw string, nominal parser/lifetime/cycle tests fail and independent native positive fails. Existing two graph constructor conversions already pass. Raw-control mutations run against real codec and fixed contract. Three annotation-mutation setups correctly refuse absent nominal declarations rather than pretending to test them.

Actual Git merge-file evidence: job117211970887 performed nine source merges; seven clean, codec has two version-port overlaps, model one import overlap. Resolve narrowly retaining current supports_feature and amendment/diagnostic imports.
