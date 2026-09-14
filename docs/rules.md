# Architecture rules

Contract 2.0 separates deterministic rules, regression checks, declarations and review claims.

| Class | Purpose | Check outcome |
|---|---|---|
| A | Enforce a fact visible in one complete observation. | PASS or FAIL |
| B | Compare accepted and candidate observations. | PASS or FAIL |
| C | Preserve review context without enforcement. | Not evaluated |
| D | Record a bounded human or LLM review claim. | HYPOTHESIS |

## Class A: deterministic rules

`forbidden_dependency` is the implemented class-A rule. The analyzer projects imports between
exact module prefixes and reports a violation when a forbidden source imports its target.

- **Measurement:** matching import records, including type-checking imports when configured.
- **Determinism:** requires a complete scan with the same contract and analyzer version.
- **Blind spots:** dynamic imports that the analyzer cannot resolve remain unknown.
- **Example:** forbid `sample.core` from importing `sample.cli`.

Additional class-A rule types are planned and are not accepted by the Contract 2.0 schema yet.

## Class B: regression checks

Regression checks compare accepted and candidate observations. They include scalar counts,
integer cross-multiplied ratios and semantic fingerprints.

- **Measurement:** `calls_unresolved`, `unresolved_ratio`, typing positions, cycles, private
  crossings, violations and coverage failures.
- **Determinism:** both observations must use comparable Python and analyzer versions.
- **Blind spots:** a stable count can hide replacement of one finding by another; fingerprints
  cover supported semantic changes, not intent.
- **Example:** reject a candidate whose unresolved call count rises from 0 to 1.

## Class C: declarations

Fields under `declarations` preserve capabilities, review scopes, public interfaces, commands,
context roots, paths and owners. Archkeel decodes and reports them but does not enforce them.

- **Measurement:** none; declaration records mirror the contract.
- **Determinism:** decoding is deterministic for a valid Contract 2.0 document.
- **Blind spots:** Archkeel makes no claim that code follows a declaration.
- **Example:** record `sample.api` as the intended public interface.

## Class D: review claims

Class D is planned. It will bind a review verdict to an evidence digest and retain the verdict as
a hypothesis rather than a deterministic gate.

- **Measurement:** none implemented.
- **Determinism:** the evidence package can be stable; the review judgment cannot.
- **Blind spots:** reviewer context, model behavior and ambiguous responsibilities.
- **Example:** review whether a component responsibility is coherent.

## Migrating from 1.1.0

Contract 2.0 keeps `components` and `rules` at the top level. Move every class-C declaration
under the optional `declarations` object:

| Contract 1.1.0 field | Contract 2.0.0 field |
|---|---|
| `capabilities` | `declarations.capabilities` |
| `review_scopes` | `declarations.review_scopes` |
| `public_api` | `declarations.public_api` |
| `public_api_provenance` | `declarations.public_api_provenance` |
| `public_commands` | `declarations.public_commands` |
| `context_roots` | `declarations.context_roots` |
| `context_roots_provenance` | `declarations.context_roots_provenance` |
| `paths` | `declarations.paths` |
| `spot_owners` | `declarations.spot_owners` |

Set `schema_version` to `2.0.0`. The optional `$schema` points to
`schema/architecture-contract.schema.json`. Omit unused declaration arrays instead of copying
empty arrays. Run `archkeel validate --root . --json` to verify the migrated contract.
