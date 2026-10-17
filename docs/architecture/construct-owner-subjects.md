# Qualified construct-owner scopes

The evaluator already matched `forbidden_construct.source` against construct-owner
qualified names, but preflight counted only module names and completion receipts
selected only modules. A real function or class guard therefore produced
RULE_WITHOUT_SUBJECTS before it could prove completion.

The existing evaluation/rules owner now shares one private selector between
preflight and receipt issuance. It projects only the canonical class/function/method
subset while reading the open symbol-kind field and requires actual symbol names
inside observed modules, including the physical `inside` scope. Named-owner
receipts cite those symbols and list only their names, without claiming the whole
containing module. Module/package receipt behavior is unchanged. Missing symbols,
foreign owners and incomplete coverage cannot produce PASS.

`rule_evaluation_facts` gains only an optional keyword `symbols=()`; old callers
retain module receipts, and omitted evidence never certifies a named owner.
This is one existing production file, net +44 lines including repository formatting,
with no new production module, schema, resolver authority, contract, allowance or cap.

## Native evidence

- Before-source RED: [38997083762 /117291904496](https://github.com/rapiddweller/archkeel/actions/runs/38997083762/job/117291904496), six expected failures and three passing negatives.
- Native construct suite: [38998007573 /117294725842](https://github.com/rapiddweller/archkeel/actions/runs/38998007573/job/117294725842), 71 PASS. Real class/function/method guards produce symbol-backed receipts; unchanged-contract source mutations FAIL. Missing and near-sibling owners, no symbol evidence, foreign modules and incomplete scans remain UNKNOWN. Both actual inside cases and real run_report are covered.
- Existing analyzer/inside/receipt/rule-yield/recorded-unknown regressions: [38998007573 /117294725760](https://github.com/rapiddweller/archkeel/actions/runs/38998007573/job/117294725760), 328 PASS.
- Quality: [38998007573 /117294725644](https://github.com/rapiddweller/archkeel/actions/runs/38998007573/job/117294725644), Ruff, formatting, strict mypy across 150 files and 11 hygiene tests pass.

- Normal writer: [38998007573 /117294725833](https://github.com/rapiddweller/archkeel/actions/runs/38998007573/job/117294725833), exit 0, no failures/diagnostics, unchanged 838 UNRESOLVED /52 typing /58 UNKNOWN /0 violations; no intent amendment is needed.
- Exact site proof: [38998007573 /117294725876](https://github.com/rapiddweller/archkeel/actions/runs/38998007573/job/117294725876), the precise signed comparison below passes.

## Honest analysis limits

The before/after source comparison uses the same current engine against the pinned
68b656668a3fdbbbe482881d0dab41ff89a21ca3 source and the fix. UNRESOLVED, type-position
and UNKNOWN ratchets are unchanged. The two new owner-field `data.get` calls are
honestly PARTIALLY_RESOLVED: their dynamic receivers have the existing
`archkeel.ir.facts.RecordData.get` candidate. PARTIAL therefore increases
2509 → 2511. The RawData API allows dictionary subclasses; ordinary `.get` semantics
are preserved instead of bypassed to force a static resolution result.

One pre-existing PARTIAL `assessment_facts.extend` call keeps its status, reason,
candidate target/count and multiplicity. Its actual call AST changes only because
the nested evaluator now receives `symbols=symbols`. The verification retains both
original ASTs and record IDs and associates only that exact checked keyword change.
Other UNRESOLVED/PARTIAL call ASTs and named payload fields are compared with signed
Counters, including targets and multiplicity. This does not claim byte equality
of all source evidence or complete resolved-call/closure payloads.

The selected UNKNOWN records retain IDs, kinds, subjects, rule IDs and complete
data, including all eight UML records. Outer evidence bytes are outside this proof.

This fix changes no architectural intent or policy files and requires no amendment.
An explicit --write-amendment nevertheless produces an optional digest binding,
even for equal before/after intent. The first writer log's optional print used an
older receipt filename; its missing print is not proof that no file was created.
The final verification reads the actual normally generated binding, checks equal
intent/baseline digests, removes that redundant verification output and validates
the committed fix without any amendment. Independent Astra review and Root's
combined/full-suite gates remain separate.
