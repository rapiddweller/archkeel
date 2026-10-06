# AD-18 A forbidden dependency supersedes the interface boundary on the same import

An import rejected by `forbidden_dependency` emits only that violation.
`interface_boundary` evaluates the remaining imports: a forbidden edge has no
legitimate interface. The violations measurement counts each rejected import once.
The analyzer version rises because the same input yields fewer records.

On the internal service, most of 149 interface violations duplicated the 148
forbidden use-case-to-persistence imports.
Check: a probe breaking both rules reports only the forbidden dependency; an
allowed pair reaching an undeclared interface still fails. Service evidence
counts each rejected import once.
