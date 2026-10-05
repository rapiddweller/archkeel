# AD-191 Source protocol Target includes resolver settings

The independent IR Target includes PythonSettings, DartSettings and
TypeScriptSettings, their public fields, ResolverSettings and PROTOCOL_VERSION.
Requests reference the resolver union. Requests and responses reference the shared version.
The module references each union variant at its evaluation scope.

Settings select a language and resolver configuration. They carry no architecture rules,
Target intent, verdicts or rendering state. Existing dataclasses and graph types are reused.
No Analyzer or renderer change is required.

These declarations require known entities and relationships. They add no closed scopes.
Existing closed SourceFacts and protocol inventories remain in force; incomplete creation
or mutation evidence stays UNKNOWN. The constant declaration checks identity and visibility,
not its runtime value.

Proof: independent intent against saved source facts, a deliberately changed language
annotation, schema validation and As-Is/Target/Diff browser navigation.
