# Native string-comparison observations

The Python collector records comparisons with a written text or bytes vocabulary.
These records describe source syntax. They do not prove the runtime type of an
arbitrary expression, evaluate imports or certify global namespace immutability.

A scoped `forbidden_construct` rule selecting `string_literal_compare` rejects:

- equality and inequality with text or bytes literals;
- membership in a nonempty literal tuple, list or set of those values;
- literal value patterns in `match`, including nested sequence patterns;
- direct, unambiguous module/class literal bindings, including `Final` annotations;
- direct named module literal collections whose visible loads are only membership;
- explicit `LocalEnum.MEMBER.value` extraction when the local enum member has a
  written text/bytes value, a direct unshadowed stdlib `Enum`/`IntEnum`/`StrEnum`
  import as its base, and no override of `value`;
- the interpreter entry comparison `__name__ == "__main__"`.

An enum member comparison or identity check remains legitimate. Its explicit
`.value` extraction does not preserve that typed control boundary. Converting a
typed value for an external API or wire payload remains a boundary operation;
this detector concerns comparisons, not ordinary serialization.

The existing lexical-scope owner distinguishes a module literal from a parameter,
local variable or shadowed class. A named collection with a second assignment,
global rebinding declaration, visible mutation or alias escape is not classified.
Its initializer must have a single assignment target; chained assignments can
publish the same mutable container through another name or attribute. Each named
load must be the final comparator of a final `in`/`not in` operation. In
`value in TOKENS == expected`, `TOKENS` also has an equality role, so that named
collection is not classified.
Mapping-pattern keys are structure; a string key alone is not a value comparison.

## Explicit limits

Imported runtime constants, arbitrary attribute properties, computed expressions,
dynamic namespace changes and collection aliases are not followed. An undecidable
value is not reported as a literal merely because its spelling resembles a keyword.
Calls such as `startswith`, substring/byte-subsequence tests and arbitrary
string-to-string data comparisons are outside this syntactic construct. The rule
therefore cannot certify a semantic ban on every possible raw protocol comparison.
No compiler, signature, member-binding or native type-proof receipt is added.

A rule PASS means that the supported syntactic construct was absent in the scoped
observation. It does not establish that imported/dynamic values are typed enums.
Ownership-specific typed APIs and independently authored Targets remain necessary.

The implementation owns this bounded classification in the Python construct
collector. It does not introduce a global protocol enum or a general-purpose
cross-module evaluator. Source mutation tests exercise actual native collection
and trace-valid violations; enum identity, arbitrary module-name data and lexical
shadowing are independent accepted controls.
