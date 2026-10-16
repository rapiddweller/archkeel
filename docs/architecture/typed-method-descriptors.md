# Typed method descriptors

Property follow-up in [#542](https://github.com/rapiddweller/archkeel/issues/542),
authorized against `4493b0a944e6caf0c56802c6333d9fd0090041b4`.

The existing source-facts owner defines `MethodKind` for the five existing
wire spellings: instance, static, class, constructor and factory. Python only
produces the first three; Dart and TypeScript retain their existing records.
A frozen `MethodDescriptor` carries the nominal kind, existing decorator/final
binding proof booleans and optional existing `PropertyBinding`.

Python's `method_descriptor` produces this value. Its provider table uses
qualified names as data and nominal effects as values; it remains subject to
the existing binding-proof predicate. Transparent overload/abstract decorators
do not count as descriptors; property counts but never resets STATIC/CLASS.
The existing `method_decorator_data` port still returns a real dict through a
thin facts-codec writer, preserving key presence and values.

`parse_method_kind(JsonValue | RawJson | MethodKind) -> MethodKind | None` classifies supported tags once.
Missing/future/off-shape values stay unchanged in the raw wire transport and
classify to None. Core retains its existing non-static receiver predicate;
None is not normalized to INSTANCE and is not additional binding proof.
The existing direct helper's required-key lookup remains required.
Graph projection maps only known STATIC/CLASS values to existing modifiers.
Property and Dart constructor-proof checks use the same nominal reader.

No parameter/visibility/definition-context/typing-role changes, new provider
enum, stricter wire schema, protocol version or resolver authority belong here.
Native tests restrict claims to descriptor controls: reserved names, record
categories and unrelated grammar in large functions remain outside this scope.

The existing RawJson alias lives upstream in facts beside frozen JsonValue; facts_codec
reexports the same alias. This names both genuine input representations without a
facts-to-codec cycle. Arbitrary non-JSON Python objects are not a promised input domain.
The input annotation remains visible to normal typing measurements; no alias to object
or measurement exception hides a new broad input position.
