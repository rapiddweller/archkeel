# AD-42 A `requires` entry may name the modules it goes through, and twelve prohibitions become that one permission

A `requires` entry gains an optional `through` list of module prefixes of
the required component; `complete_requires` then covers an import only when the imported module
falls under one of them, and an import of any other module of that component is the violation
it already was for a component never required at all. The analyzer's entry reads
`{"component": "ir", "through": ["archkeel.ir.model", "archkeel.ir.codec"]}`, which is [AD-4](ad-04-module-length-alone-does-not-justify-a-split.md)
stated where the dependency is stated, and the twelve `DEP-ANALYZER-NO-IR-*` rules that said the
same thing one `ir` module at a time are gone. Reason: the twelve rules were a blocklist, so
each module `ir` gained since (`references` with [AD-26](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md), `levels` with [AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)) had to be remembered
by hand or was silently open to the analyzer, while `tests/test_self.py` held the real allowlist
as a test; the entry's own rationale already said "through the common model and codec boundary",
so the contract had the decision in prose and enforced its complement. Rejected: an
`allowed_targets` field on `forbidden_dependency` with `source: archkeel.analyzer, target:
archkeel.ir`, because a rule whose source and target are exact component packages decides the
pair ([AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md)) in the analyzer's matcher, in `ir.decisions` and in `check.validation`, so all
three would need to learn that this one narrows instead of decides; `through` touches one
evaluation and changes no pair semantics, since absence still decides. Limit: `through` narrows
by module prefix, not by symbol, so `archkeel.ir.model` admits every name the module defines; a
prefix naming a module of a different component covers nothing, the same blind spot a `requires`
entry naming an unknown component has; and the projected declaration record still lists only the
required component, so the observation shows the edge but not its width. Check:
`tests/test_analyzer.py::test_a_requires_entry_covers_only_the_modules_it_goes_through`,
`tests/test_self.py::test_self_contract_covers_modules_and_analyzer_interface` reading the
allowlist from the contract instead of a constant, and `validate` naming an unknown `through`
module at `/components/<n>/requires/<m>/through/<k>`.

