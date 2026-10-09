# AD-215 Preserve Dart source evidence

Keep native-compatible input hashes, generic base lookup, complete member spans,
and lexical ownership of initializer reads. Calls retain their callable scope;
awaited results are not treated as direct call results.

Complete the syntax Target with Member and Parameter DTOs and their typed links.
Component permissions and shared protocol definitions stay unchanged.

The self-scan measures 921 unresolved calls, up from 915: five string operations
in nominal type lookup and one bytes join for the input digest. These are existing
Python inference limits for external standard-library receivers. Bind that exact
measurement; retain all other budgets and zero architecture violations.

[Bound amendment](ad-215-dart-source-evidence-amendment.json).
