# AD-434: Named type publication needs a direct witness or one same-name hop

Status: accepted

## Context

AD-428 keeps included type-only imports UNKNOWN without publication proof.
The TypeScript corpus has 12 such interface rules and 36 affected import records.
Each record needs a direct type publication or one named type re-export hop.

## Decision

The collector keeps type publication separate from the existing value witnesses.
It proves a directly exported interface or type alias with one root declaration.
Any second same-name declaration prevents this type proof, including a class or namespace.
The collector also checks the unique source binding and rejects import aliases.

A named type re-export can add one same-name hop to a direct proof.
Both `export type { X } from` and `export { type X } from` are supported.
The resolver must name the exact file of the hop and the declaration.
The collector records a binding witness and source evidence for each publication.
The import cites these witnesses and keeps the ordered publication names in `reexport_chain`.
No new fact field or wire version is needed.

The model accepts an included named type only with a known binding and this bounded route.
The existing public selectors still decide whether that route is public.
A proven direct import of a private type gives FAIL under the same conditions as a value import.
An unrelated public type with the same name cannot authorize the private import.
`Scope::complete` still checks coverage, gaps and the unchanged `receipts::ownership` proof.
The existing makers remain the only way to create PASS.
Type publication does not lift the existing dependency-symbol limits.
Included type-only symbol ports and nonmatching forbidden symbols stay undecided.

The new typed gap is `InterfaceGap::TypePublication`.
It names an unproven named type publication, not a lifecycle result.
The collector preserves existing value, overload and script-global facts.
Only proven type import proof fields, new binding witnesses and their evidence change.

## Alternatives and limits

Do not accept a type because the public module contains the same text.
Do not search other modules for a matching name.
Do not make the value declaration guard stricter to obtain type proof.
Aliases, star exports, namespace exports, default exports and merged declarations remain UNKNOWN.
More than one hop, local export clauses and unwitnessed declarations remain UNKNOWN.
An unrelated unsupported export can prevent type proof for the whole module.
This conservative limit avoids an export-surface inference.
Public-interface lifecycle checks and facade signatures remain outside this import verdict.

## Checks

`tests/test_cli_native_type_publication.py` plants direct types, one-hop types and unproved forms in the release core.
It also checks private types, same-name types in separate modules and unowned sources.
Collector tests retain exact value, overload and script-global records.
Five named golden cases add only the new type proof fields, witnesses and evidence.
The profile probe now expects PASS for its witnessed public types.
The native self-row and expected-gap tests retain their unchanged pins.
