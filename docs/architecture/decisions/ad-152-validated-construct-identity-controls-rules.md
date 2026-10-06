# AD-152 Validated construct identity controls rules

Dispatch construct rules on validated `data.construct`, the identity used by
Core capability validation. Descriptive record kinds cannot decide policy;
doing so could hide an accepted assert fact.

Keep legacy kind mapping only for older typing signals without a construct field.
Preserve record spelling, exemptions, capability refusal and traceable violations.
Requiring one descriptive spelling would restrict the replaceable port without
adding evidence.

[Capability proof](../../../tests/test_collection_capabilities.py).
