# Issue 542: typed TypeScript syntax boundary

## Design and ownership

The existing parse.py is the only Tree-sitter consumer. It currently exports frozen lexical DTOs whose closed fields are Literal/string values, and collect.py branches on those values. Move these existing DTOs, without copies, into one coherent syntax.py port. It owns plain nominal ReferenceForm, DefinitionKind, Visibility, BaseRelationship, SiteKind, SiteUse and ReceiverKind domains. Parser nodes and grammar implementation remain private to parse.py. Collector-owned resolution and inventory states remain local to the collector instead of introducing a global enum module.

A private parse-boundary kind adapter decodes each Tree-sitter node kind once into the parser's closed vocabulary. Unknown node kinds remain explicitly unknown and cannot match a known declaration or establish complete member inventory. The collector consumes already typed semantic DTOs; it does not infer a known category by reparsing parser text. In particular the receiver's special this category is established from the decoded syntax kind, while its actual receiver spelling remains string data.

Open declaration names, paths, annotations, Query-Capture keys and named parser fields stay lookup data. Closed syntax categories, syntax modifiers, loader/constructor control tokens and grammar alternatives must not dispatch on strings. Existing literal/escape handling uses actual decoding or grammar parsing where appropriate, with existing conservative behavior preserved. Enum values are serialized only at fact/ID/wire boundaries; no .value comparisons or renamed constant dispatch is introduced.

## Boundaries and enforcement

The source component owns parse.py and syntax.py and publishes a named syntax DTO port plus parse(). The entry/collection component requires source and uses this port. Root enum placement intent gains the actual local vocabulary owners. Independent authored Target entities bind selected closed enum/API fields and signatures. Actual-source type widening and equality, membership (including literal left), alias and match mutations must fail against fixed intent.

Complete parse/collect guards are claimed only after a real native positive observation with the new observer succeeds. There is no new observation authority, parser/protocol exception or accepted debt. Any genuinely uncompleted domain must remain explicitly listed rather than concealed with narrowed evidence.

## Sequence

1. Checkpoint this design before implementation; finish the smaller independent has_field increment first.
2. Add focused semantic nominal-type checks and native fixed-contract RED controls on actual predecessor source.
3. Move, do not duplicate, existing DTOs and implement owner-local parser decoding; update the single collector boundary.
4. Preserve existing compiler/config/differential corpus; adapt Python API tests to nominal identity and verify unknown-node conservatism.
5. Run focused complete TypeScript suites, pinned compiler differential, native own positive/mutation checks, Ruff/mypy, hygiene and baseline without increased limits. Apply exported formatting to product.
6. Deliver a clean independent commit and evidence to parent for independent final Astra review, integration amendment and merge.
