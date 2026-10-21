# AD-255: `validate --against` reports narrowings

A contract review needs the whole semantic change, not only what requires an amendment.
`validate --against` adds `contract_changes`: each contract change with its direction
(`widened` or `narrowed`), subject, field and message. `widenings`, `failures`, the
amendment gate and exit codes are unchanged; only widenings still fail.

Narrowings are reported for: a removed `requires` entry, a new `requires` entry contained
in the old permission (AD-245), a removed `public` entry, an added restriction rule and a
removed permission rule. Other narrowing changes (budgets, rule fields, ownership) are not
enumerated yet; their absence in `contract_changes` proves nothing.

The field is present only with `--against`, so every other result keeps the 9.0 shape.
`command-result-10.0` describes it; published schemas stay byte-exact (AD-138). Baseline
and measurement-budget changes stay in `widenings` and `failures` only.

[Narrowing controls](../../../tests/test_widening.py)
