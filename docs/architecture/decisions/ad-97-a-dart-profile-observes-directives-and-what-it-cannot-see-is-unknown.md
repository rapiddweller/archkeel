# AD-97 A Dart profile observes directives, and what it cannot see is UNKNOWN

The Dart profile observes directives, not symbol usage. `show` proves listed names; imports without
it prove edges but leave names unknown. Unsupported rules and invalid syntax exit two; unavailable
measurements stay null, and dependent claims stay UNKNOWN.

Resolve own package imports from the declared namespace, not untracked package configuration. Keep
generated imports and conditional alternatives as real edges. Proof:
[test_dart_profile.py](../../../tests/test_dart_profile.py) and
[test_dart_rules.py](../../../tests/test_dart_rules.py).
