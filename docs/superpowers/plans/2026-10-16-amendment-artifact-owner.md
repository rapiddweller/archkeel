# Amendment artifact owner — issue #542

Parent approved this bounded implementation on b475e027f4384feb8cdf2cc9844b82cdf89185ea after the read-only Core inventory. Use Superpowers TDD/verification inline; the parent obtains independent Astra review before merge. Work on an isolated remote branch and hosted Actions only.

Goal: one owner for the existing immutable Amendment value, its supported versions and exact digest-binding verification. Preserve valid legacy constructors, published JSON bytes, import identities and free-form decided_by/rationale. Own valid/stale separately from assessment verdicts.

## Planned changes
- Create ir.amendment with AmendmentVersion, AmendmentStatus, Amendment and verify_amendment. Keep widening's exact-class/function compatibility reexports.
- Extract the existing artifact parser/writer into ir.amendment_codec; codec_governance and codec keep identity-preserving reexports. Parse the closed wire version once, preserving unsupported-version errors.
- Change only RunResult.amendment_status and its direct validation producers/consumers to the canonical status type. Do not migrate other Result, Command, Delta or Measurement controls.
- Publish narrow actual API entries within existing IR/governance responsibilities. Author independent Target fields/signatures and whole-module string-control guards for the two fully migrated artifact modules; do not claim whole-model/governance string freedom.
- Preserve schema bytes, policy/baseline values, proof/hash algorithms, grant/Language/Graph/Version corrections and the recent primitive wire fix.

## TDD and verification
1. Commit this plan first. Add independent authored Target/API intent, fixed wire/legacy/identity tests, native source-widening and raw-dispatch controls.
2. Hosted RED on unchanged production must demonstrate missing nominal owner/protection. Historical amendment tests remain unchanged.
3. Implement the extraction and actual producers; keep old wire spellings, v1 contract-only behavior and v2 baseline binding.
4. Hosted GREEN: focused native mutations, bound-amendment/widening/schema/CLI regressions, Ruff, strict Mypy and hygiene.
5. Run real own validation against b475 with a normal amendment, unchanged budgets. Compare individual type-UNKNOWN, unresolved and PARTIALLY_RESOLVED call sites with multiplicity and target evidence, distinguishing moved code from new debt.
6. Commit the normal receipt; rerun exact NoWrite validation. Freeze a clean product ref/file list with evidence for parent/Astra. Do not start another Core stage.

The public command schema remains four-valued, CLI dispatch remains six-valued, and future Delta dimensions/change labels remain open wire data; none belong to this increment.

## Execution ledger
- Plan committed before code: 3fa4e24.
- Hosted RED 38964695412 / 117188142018: 26 failed, 8 passed on unchanged production; nominal owner/codec absent and native guards have no subjects. Original wire errors/binding cases remain passing.
- Ruling: split the existing artifact codec from the model-free value owner because codec_wire imports model; combining them creates model→amendment→codec_wire→model. Reuse shared validators and keep old facade function identity instead of duplicating validators.
