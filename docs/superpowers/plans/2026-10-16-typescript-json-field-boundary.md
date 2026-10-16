# Issue 542: TypeScript JSON field presence

## Design and scope

The existing config module owns JSON input decoding and the open Json mapping type. Structural field names (baseUrl, paths, references, typesVersions) are data keys, not closed mode or syntax dispatch. Presence differs from a missing value: explicit null and falsy values must still count as present. A single public has_field(record: Json, name: str) -> bool will own this open mapping operation, using variable-to-variable key identity. No compiler mode, source kind, grammar token or protocol-state dispatch moves into this API. No duplicated key enum or parser/protocol allowance is introduced.

Consumers are precisely config._overlay (baseUrl and paths), config.load_config (references), resolve._package and resolve._worker (typesVersions). The configuration component publishes the named API and an independently authored UML method signature binds its two inputs and bool result.

## Sequence

1. Commit this plan before implementation.
2. Add missing/null/falsy/present regression cases and authored Target; run hosted RED on predecessor implementation.
3. Add has_field and migrate the five actual consumer sites; add return-type mutation and literal-on-left protocol mutation controls against the fixed contract.
4. Run focused config/resolver/native controls with the new native observer, lint/mypy, and native baseline without increasing limits. Keep the pinned compiler/differential corpus unchanged. Export and apply formatter patches before the clean product commit.
5. Record exact evidence and limitations for independent final Astra review and parent integration. b82eb441 remains the immutable previously verified predecessor.

## Scope boundary

Tree-sitter node kinds and parser/collector semantic values remain a subsequent independent issue-542 increment. This change does not claim those untyped domains are migrated.
