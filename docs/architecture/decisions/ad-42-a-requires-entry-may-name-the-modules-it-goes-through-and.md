# AD-42 A `requires` entry may name the modules it goes through, and twelve prohibitions become that one permission

A requirement's optional `through` list restricts imports to module prefixes in the
required component. `complete_requires` rejects imports outside them. The analyzer
requires `ir` only through `archkeel.ir.model` and `archkeel.ir.codec`, enforcing
[AD-4](ad-04-module-length-alone-does-not-justify-a-split.md) at the dependency entry.

Remove twelve `DEP-ANALYZER-NO-IR-*` blocklist rules. New modules such as `references`
([AD-26](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md)) and `levels`
([AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)) had needed manual
prohibitions, while a test held the actual allowlist.

Putting `allowed_targets` on `forbidden_dependency` would require three pair-decision
readers to distinguish narrowing from deciding
([AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md)). `through`
changes one evaluation without changing absence-as-prohibition semantics.

Limits: prefixes admit all module symbols; a prefix in another component covers
nothing, like an unknown required component. Originally the projected record
showed only the endpoint, not the narrower permission.
Checks: `tests/test_analyzer.py::test_a_requires_entry_covers_only_the_modules_it_goes_through`,
`tests/test_self.py::test_self_contract_covers_modules_and_analyzer_interface` reads
the contract allowlist, and validation locates unknown prefixes at
`/components/<n>/requires/<m>/through/<k>`.
