# AD-191 Source protocol Target includes resolver settings

Declare resolver settings, their union and protocol version in the independent
Source protocol Target. Requests and responses reference shared types and version;
settings carry language/configuration, never policy, verdicts or rendering state.

Require known entities and relationships without adding closed scopes.
Existing closed inventories remain in force; incomplete creation or mutation
retains UNKNOWN. Constant identity and visibility do not prove its runtime value.

[Protocol Target proof](../../../tests/test_protocol_uml_target.py).
