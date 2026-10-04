# AD-22 The analyzer is a process port with a language profile

## Target, clarified 2026-10-03

Each language adapter is a configurable executable. It owns parsing, project
resolution and source-fact extraction. One versioned JSON request enters stdin;
one factual response leaves stdout. Diagnostics use stderr. No shell command,
plugin discovery or daemon is required.

The Core validates facts, profile capabilities, coverage and provenance against
the common/profile schema. It owns assignment, rule evaluation, evaluator
receipts and verdicts, then produces the canonical observation. The adapter
does not receive architecture policy or emit policy verdicts. Reuse the existing
IR's factual records rather than inventing a parallel final-result format.

Python, Dart and TypeScript use the same port. Python-specific AST objects stay
inside its adapter; Dart keeps its limited directive capabilities. The Core
remains implemented in Python and owns policy evaluation.
Full Dart type/construct analysis is not required to establish replaceability.

Capabilities, runtime and file/selector identities are profile-aware. Analyzer
identity and digests still decide comparability
([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).
Unknown identities, missing evidence and protocol failures cannot grant PASS.

## Implementation and acceptance

The process port, separate Python/Dart adapters, shared source facts and Core
evaluation are implemented. TypeScript uses the pinned npm collector under
`packages/typescript-adapter/`, with its own source contract. Its import-only
capabilities and packaging are defined in
[the decision](../typescript-foundation-proposal.md).

Acceptance requires Python/Dart semantic parity, replacement by a configured
executable and refusal of invalid facts, incompatible profiles and unavailable
tools. See [configured collection](../../../tests/test_collection_process.py),
[wire conformance](../../../tests/test_collection_conformance.py),
[collector facts](../../../tests/test_language_collectors.py) and
[boundary regressions](../../../tests/test_collection_boundary_regressions.py). Integrated local gates and
cross-platform CI remain required; source implementation does not prove publication.

## Future boundary

HTTP calls and queue publication/consumption are distinct from imports. Future
interaction observers may link explicit API/channel/schema identities across
languages and repositories. Keep intended declarations, source-backed usage
and observed runtime traffic distinct. No such observers or rules are implemented
by this decision; the TypeScript scope only preserves that boundary.
