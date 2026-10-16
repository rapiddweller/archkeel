# Typed control migration scope

The native `DEPENDENCY-TYPED-CONTROL` rule protects the complete
`archkeel.ir.dependency` policy module against `string_literal_compare`.
It uses the existing AD-48/AD-80 analyzer and evaluator. There are no
`allowed_sources`, exact-source exemptions, new lint engine or debt allowances.

The protected vocabulary is selector match mode and dependency target kind.
Its owner defines `SelectorMatch` and `DependencyTargetKind`; matching branches
consume their enum members. Core and projections use that same selection API.
A string constant or `Final[str]` is not a replacement for these types.

Native controls add real Python code to the protected source module. Literal
equality, collection membership, `match` and a local `Final[str]` disguise each
produce a trace-valid violation under the unchanged own contract. Enum branches
and comparisons between module-name data pass. A wire-kind comparison in the
codec remains observed and accepted outside the policy boundary.

## What is and is not certified

| Responsibility | Owner and guarantee |
| --- | --- |
| Closed dependency selector modes | `ir.dependency`: owned enums, independently declared API types and native string-control prohibition |
| Contract/record wire conversion | `ir.codec_contract`: strict conversion to the shared types; input grammar and JSON keys remain string data |
| Rule verdicts and receipts | Core: existing evaluator consumes the shared selector; report projections do not reconstruct modes |
| Module, package and symbol identities | String data; matching compares supplied names and uses the shared dotted-name primitive |
| Other behavioral vocabularies | Existing typed aliases and enums remain; this change does not certify their complete migration |

At Main `63437df6734275850838ba1026b276c2f930bf2f`, the native audit
observed 1,662 string-literal comparisons across the repository. This is a syntax
count, not 1,662 proven design defects. Examples needing different treatment:

- Dependency mode comparisons were domain control and now use the shared enums.
- `codec_contract.parse_contract` tests external rule kinds and encoding versions
  at its input boundary.
- TypeScript and Dart parse modules recognize source-language tokens.
- Graph assessment/status and relationship-kind branches use other existing
  vocabularies; their broader enum migration and protection are outside this
  bounded dependency-policy guarantee.

Green CI proves the declared protected scope. It does not prove that every
Archkeel component is free of string dispatch. The independent inner-Target work
in #340 remains broader than this API. Further migrations should establish one
cohesive vocabulary owner and native controls before enlarging the protected
source scope; copying all literals into one repository-wide enum would hide
responsibilities rather than clarify them.
