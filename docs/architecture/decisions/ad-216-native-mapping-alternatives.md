# AD-216 Native mapping alternatives retain their union proof

For [issue #430](https://github.com/rapiddweller/archkeel/issues/430), retain a
private proof of alternative mapping arms before boundary findings are combined.
The existing type shapes and proven bindings must establish string keys, clean
string-valued arms and exactly one supported native `object` or `list[object]`
value. Count occurrences before deduplication; reject aliases, unknown arms,
object keys and simultaneous nested maps.

Existing exact callable, position, complete annotation and optional field path
select this union. Outer-map permission and native-value depth remain separate.
DTO fields still require one declaration; depth includes preceding containers.
A union inside another container does not prove that container's full annotation.

Keep public schemas, selectors, legacy IDs and single-map behavior unchanged.
Only the native value fact records accepted opacity; other findings and UNKNOWN
remain. [Proof](../../../tests/test_boundary_type_alternative_maps.py).
