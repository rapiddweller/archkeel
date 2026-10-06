# AD-146 Analyzer identity selects the observation profile

Select exactly one observation profile from the published analyzer identity.
Unknown identities are invalid; never infer Python capabilities from an unfamiliar
producer. Unmeasured sections stay null according to that profile, rather than
empty arrays suggesting a clean measurement.

Python requires arrays throughout. Dart omits symbol/reference/binding measurements;
TypeScript additionally omits call, typing and construct measurements. Synthetic
observations follow the same identity contract.

[Codec proof](../../../tests/test_codec.py).
