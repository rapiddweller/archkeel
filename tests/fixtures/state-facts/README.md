# State collection oracle

Captured from unchanged `embedded/contexts.py` at base `44014ce` / type-fact commit `af1d975` before routing collection through the new adapter/Core split.

- `contracts.json`: one source, two root selections; fields, frozen/property/mutation facts, nested traces, missing roots, binding precedence.
- `duplicate-names.json`: competing simple names, positional-only receiver behavior, nested class ownership. Reversed declarations reuse the same expected result.
- `private-attributes.json`: Any alias, shadowed alias, nested private access.

Evidence includes only the locations added by the original Context collector; ordinary symbol/import/call evidence is supplied separately. Fixtures contain no runtime paths or timestamps. Final tests never execute the old collector.
