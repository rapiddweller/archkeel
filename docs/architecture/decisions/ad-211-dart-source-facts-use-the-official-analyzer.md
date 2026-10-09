# AD-211 Dart source facts use the official Analyzer

Superseded by [AD-214](ad-214-dart-collector-runs-without-sdk.md): the collector now runs in Python.

Run one pinned official Analyzer collector through the shared source-facts protocol. Core owns
comparison and rules; the shared graph and report own presentation. The authored Target stays
independent of source observations.

The collector records syntax declarations, members, signatures and statically resolved sites.
Dynamic dispatch, missing resolver inputs, malformed units and unsupported declarations remain
UNKNOWN. Python-only rules and unmeasured budgets stay unsupported or UNKNOWN.

Use Dart SDK `>=3.9,<4` and run `make dart-setup` before Dart scans. Package identity comes from
`pubspec.yaml`; configured scan namespace and available resolver inputs remain separate facts.

[Nested Dart acceptance](../../../tests/test_dart_uml_acceptance.py), [native collector](https://github.com/rapiddweller/archkeel/blob/a7ef862f/src/archkeel/analyzer/dart/native/README.md), and [UML model](../uml-model-target.md).
