# AD-307 A Git manifest composes the system landscape

**Status.** Issue #853 architecture decision. No runtime implementation is selected.

**Decision.**
- The Git-versioned root architecture contract may itself be the system manifest and entry point
  for a top-down view. Prefer its existing optional `declarations.uml` Target section and shared
  Target graph owner for typed runtime units, external systems, directed communication intent, and
  references to existing component owners. Resolve references to unique owner identities through
  that graph; if the current linker cannot bind an owner, extend it in place rather than copying
  the definition. Do not assume a separate sidecar manifest or parser.
  It may describe an empty greenfield system and use multiple system,
  runtime, and component levels. Share submodels only through explicit references when needed;
  multiple runtime units may reference the same component without copying its definition. No
  directory or contract tree is mandatory. Contract definitions stay in their current files and
  have one owner.
- Resolve the root contract and every referenced contract from one immutable Git revision, or one
  explicitly identified immutable snapshot such as an uncommitted design draft. A result identifies
  that revision or snapshot content. Never mix states. Missing, ambiguous, or invalid references
  are errors or UNKNOWN; never silently resolve them from another state.
- Project this composition through ArchKeel's existing Target/Observed graph owner. A later
  implementation must add nominal kinds for runtime units, external systems, and communication
  where needed. Communication is a directed Target relation, distinct from source `IMPORTS`,
  `CALLS`, and component containment. Imports or calls alone do not establish a runtime flow;
  combined, unambiguous evidence may support one in a later implementation.
- Keep declared architecture intent distinct from deployment declarations and observed facts.
  A deployment target may distinguish environments and says what should be placed where; an
  observation proves only what its evidence covers. Known communication protocols may be recorded
  when available. Agent inference stays separate from both Target and observation. Incomplete or
  unavailable evidence remains UNKNOWN. A manifest never asserts an unobserved data flow as fact.
- Use Git as storage and history. Do not add a database absent a measured query or scale need.
  Top-down drilldown follows the manifest's contract references and then each contract's existing
  component hierarchy; it does not create a second policy or graph API.

**Alternatives.** Adding system/runtime relationships directly to `components[]` would mix them
with source ownership and contract-level `requires`; the existing separate `declarations.uml`
Target section is a valid and preferred place for this intent. `inside` mounts a scoped contract
tree and does not provide reusable sharing; `requires` grants component import permission. Neither
is a system-link mechanism. A separate database would duplicate Git history and add an unproven
consistency owner. None is justified.

**Limits.** This decision does not define a manifest schema, graph wire version, deployment format,
evidence collector, API, or UI. Those require a public greenfield fixture and validation through the
existing graph/contract owner. No real system topology or communication is asserted here.

**Basis.** AD-111 owns recursive `inside` loading; AD-113 and AD-164 define `requires` as
contract-scoped import permission; AD-161 and AD-173 keep Target intent separate from observed
source facts; AD-183 binds references to one declaration; AD-291 separates call-graph evidence from
external-system claims; AD-304 keeps planned component identity stable through implementation.
