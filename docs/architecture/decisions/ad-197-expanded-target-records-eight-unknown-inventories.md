# AD-197 Expanded Target records eight UNKNOWN inventories

The reviewed Target adds eight closed member scopes: `ir:source-facts`,
`ir:coverage`, `ir:snapshot`, `ir:scope`, `ir:request`, `ir:response`,
`ir:error` and `check:port`. Their declared members match. Python cannot prove
these inventories complete, so Core retains eight completeness UNKNOWNs.

The existing 40 boundary-type UNKNOWN positions are unchanged. Accept exactly
these eight additional positions for the reviewed migration: the UNKNOWN ceiling
becomes 48. This is new tracked debt, not complete architecture proof. Keep the
closed scopes and collector limits; do not turn UNKNOWN into PASS. Any further
increase still fails the baseline gate.

The v2 amendment binds the exact recursive contracts and before/after baseline.
`tests/test_protocol_uml_target.py` pins all eight subjects and the unchanged
boundary count. Complete self-Target work remains tracked in issue #340.
