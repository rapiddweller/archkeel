# AD-307 A Git manifest composes the system landscape

**Status.** Issue #853 architecture decision. No runtime implementation is selected.

**Decision.**
- Keep a small, Git-versioned system manifest as the entry point for a top-down view. It names
  typed runtime units, external systems, directed communication intent, and references to existing
  component contracts. Contract definitions stay in their current files and have one owner.
- Resolve the manifest and every referenced contract from one immutable repository revision. A
  result identifies that revision. Missing, ambiguous, or invalid references are errors or UNKNOWN;
  never silently resolve them from the working tree or another revision.
- Project this composition through ArchKeel's existing Target/Observed graph owner. A later
  implementation must add nominal kinds for runtime units, external systems, and communication
  where needed. Communication is a directed Target relation, distinct from source `IMPORTS`,
  `CALLS`, and component containment. Do not infer a runtime flow from code imports or calls.
- Keep declared architecture intent distinct from deployment declarations and observed facts.
  A deployment target says what should be placed where; an observation proves only what its
  evidence covers. Incomplete or unavailable evidence remains UNKNOWN. A manifest never asserts
  an unobserved data flow as fact.
- Use Git as storage and history. Do not add a database absent a measured query or scale need.
  Top-down drilldown follows the manifest's contract references and then each contract's existing
  component hierarchy; it does not create a second policy or graph API.

**Alternatives.** Extending component contracts alone would mix system/runtime relationships with
source ownership and contract-level `requires`. Using `inside` or `requires` for system links would
change their established meanings: `inside` mounts another contract level, while `requires` grants
component import permission. A separate database would duplicate Git history and add an unproven
consistency owner. None is justified.

**Limits.** This decision does not define a manifest schema, graph wire version, deployment format,
evidence collector, API, or UI. Those require a public greenfield fixture and validation through the
existing graph/contract owner. No real system topology or communication is asserted here.

**Basis.** AD-111 owns recursive `inside` loading; AD-113 and AD-164 define `requires` as
contract-scoped import permission; AD-161 and AD-173 keep Target intent separate from observed
source facts; AD-183 binds references to one declaration; AD-291 separates call-graph evidence from
external-system claims; AD-304 keeps planned component identity stable through implementation.
