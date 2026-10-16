# Typed control migration scope

Issue #542 includes domain control, parser grammar and protocol control strings.
Known kinds, modes, states and versions must be converted into their owned types;
parser placement is not an exception. Module names, supplied paths, identities and
ordinary text remain data. JSON lookup keys and serialized values keep their wire
spelling.

The migration proceeds in independently reviewed increments. A green rule proves
its actual source scope; it does not certify an unprotected module.

| Responsibility | Current owner and guarantee |
| --- | --- |
| Dependency selector modes | `ir.dependency`: owned enums, independent API Target and native string-control prohibition |
| State field and access controls | `ir.state_facts`: five owned enums, independent Target annotations and native prohibition |
| State event grammar | `ir.state_codec`: private event tag, one typed conversion and the same native prohibition |
| Contract/record grammar and versions | `ir.codec_contract`: remaining raw control dispatch is pending #542 migration, not permitted as a parser exception |
| Collector and source-language grammar | Profile-owned protocol/parser types and native protection remain pending migration |
| Graph and assessment vocabulary | Existing typed aliases remain; nominal migration and native protection are pending |
| Supplied module, package and symbol identities | String data compared using the shared identity and ownership primitives |

The three protected modules use `forbidden_construct` selecting
`string_literal_compare`, without allowed-source exceptions or debt allowances.
Their native controls insert equality, membership, match and Final-string branches
into actual source. Protected parser branches fail just as protected domain
branches do. A named string constant is not a nominal type.

The dependency-only test fixture deliberately checks that its one guard does not
claim protection over other modules. That cross-scope check is not a statement
that raw parser dispatch is acceptable. State parser negative controls separately
prove the real codec prohibition.

At Main `63437df6734275850838ba1026b276c2f930bf2f`, the native audit observed
1,662 string-literal comparisons across the repository. This is a syntax count,
not 1,662 proven design defects, and it is not a count of fixes in this increment.
Remaining contract, graph and profile/parser migrations must preserve wire
compatibility, establish the appropriate vocabulary owner and add native
controls before their scope is marked complete.

The broader independent inner-Target work in #340 also remains open. Each
migration must keep the owning API explicit; putting every protocol and domain
literal into one global enum would obscure those responsibilities.
