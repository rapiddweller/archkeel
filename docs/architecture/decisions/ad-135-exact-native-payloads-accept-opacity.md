# AD-135 Exact native payloads accept opacity

CE converters preserve native values such as Decimal, datetime and custom
objects. Narrowing them to JSON changes behavior; wrapping `object` adds no
type evidence. Issue #229 therefore uses the existing exact position decision:

```json
{"qualified_name": "sample.Converter.convert", "position": "value", "annotation": "object"}
```

The default broad-type violation remains. Only the exact symbol, position,
empty/omitted root path and literal `object` annotation match. Accepted input
opacity never permits its return, constructor context, masks or other methods.
Unproven class/generic annotation bindings remain UNKNOWN; inherited methods use
the declaring base scope. Bare mappings remain rejected.

The existing allowance fact/table records `accepted_opacity: true`, source
evidence and owning decision provenance. Its title says type closure remains
unproven; contract conformance does not certify a statically closed payload.
Adding a position widens the contract and requires an amendment under `--against`.

`tests/test_boundary_type_native_payloads.py` checks 15 inputs and three returns
while 18 neighbors remain forbidden, plus malformed/changed selectors and
UNKNOWNs. Native-payload/control catalog variants produce ordinary reports.
The analyzer version rises to `0.64.0`; existing contract digests stay unchanged.
