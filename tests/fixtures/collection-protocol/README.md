# Collection protocol examples

These frozen 1.0.0 packets guard legacy compatibility. Protocol tests generate 2.0.0
packets and use the frozen runtime schemas to prove the old strict boundary.
The decoder also checks identities, references, scope and coverage.

`response-python.json` deliberately has partial capabilities. It is valid wire data; Core refuses to treat it as a complete Python profile.

Policy input and dangling evidence are negative cases. Neither may become a complete observation.

`runtime.required` uses PEP 440 for Python; other runtimes allow `||` alternatives.
`capabilities.constructs` lists `{name, status}`; absent names are unsupported.

Partial collections carry an UNKNOWN coverage gap.
Distribution versions are labels; `code_digest` identifies executable code.
