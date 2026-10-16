# Contract rule grammar finalization — issue #542

## Goal and architecture

Finish the bounded nominal contract grammar on e5215b1403d98522003220b4c240aae9b011575f (property-inclusive Root predecessor). Reuse graph-owned ArchitectureRuleKind and DecisionMaker. A fieldless ArchitectureRuleGrammar mixin owns the two idempotent constructor conversions for twelve model and two graph rule DTOs; frozen/slotted field order stays unchanged. Model retains CompatibilityLifetime and CycleLevel. No generic normalization registry, new resolver authority, Record.kind inventory or JSON-key enum.

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
- [x] 2. Three-way merge only the original grammar delta, resolve current-owner overlaps, add the approved fieldless mixin and direct legacy constructor normalization.
- [ ] 3. Run contract, selector, boundary and native API/guard tests; Ruff, strict mypy and hygiene. Compare complete UNRES/PARTIAL sites and UNKNOWN IDs; preserve/tighten only measured ratchets.
- [ ] 4. Union onto the final parent supplied by Root; generate a fresh normal amendment against that exact commit, then no-write verify unchanged source.
- [ ] 5. Freeze intended source and authored intent separately, report line costs and exact evidence, hand off for independent Astra review before merge.

Pre-flight: model consumes the graph grammar owner; codec consumes those nominal DTOs; native fixtures must copy the real mixin owner. The current model has no separate ContractRuleKind, and reflective RULE_KINDS is the sole remaining get_args/get_type_hints use.
Ruling: use one explicit fieldless owner instead of fourteen repeated normalizers; the existing graph module publication already covers this named API, so do not broaden a module boundary.

Task 1: complete — plan2626c158, tests9741c00a. Hosted RED38971885025/job117211971106:39failed/21passed; twelve model direct positional constructors retain raw kind, optional component decision retains raw string, nominal parser/lifetime/cycle tests fail and independent native positive fails. Existing two graph constructor conversions already pass. Raw-control mutations run against real codec and fixed contract. Three annotation-mutation setups correctly refuse absent nominal declarations rather than pretending to test them.

Actual Git merge-file evidence: job117211970887 performed nine source merges; seven clean, codec has two version-port overlaps, model one import overlap. Resolve narrowly retaining current supports_feature and amendment/diagnostic imports.

Task 2: complete — approved fieldless ArchitectureRuleGrammar shares the two canonical conversions across14DTOs; no dataclass fields or constructor order change. Graph's two duplicated postinits disappear. Optional component attribution, shim lifetime and cycle default normalize at their own local boundaries. All14 explicit positional constructors, enum identity, replace and frozen/slots controls pass.
Task 3: compatibility/native610passed in38972250961/job117213168591; strict Ruff489/mypy148/hygiene11 green in38972471058/job117213882490. Formatting blobs retained in fdec9fd0.
Ruling: arbitrary multiply-invalid document error ordering is not a promised complete compatibility surface; preserve specific diagnostics and existing selector/module-path priority controls, without adding deferred-error infrastructure.
Actual final union:38972870856/job117215213769 ran Git merge-file for all9sourcepaths onto e5215b1403d98522003220b4c240aae9b011575f, all conflict-free and byte-identical to reviewed grammar source. Preserve property/artifact Target additions and the865 unresolved ceiling; append only47grammar Target entities and one actual-codec guard.
Diagnostic harness correction: RecordData is not iterable. The first site run measured865/58/52/0 on both sides, then failed during evidence extraction. Use the existing record_payload codec for complete record data; do not claim the incomplete run as a passed site gate.
