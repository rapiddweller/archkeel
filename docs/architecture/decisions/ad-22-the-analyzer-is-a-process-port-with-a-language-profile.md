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
remains implemented in Python, but existing scanner/policy coupling must change.
Full Dart type/construct analysis is not required to establish replaceability.

Capabilities, runtime and file/selector identities are profile-aware. Analyzer
identity and digests still decide comparability
([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).
Unknown identities, missing evidence and protocol failures cannot grant PASS.

## Current gap and proof

The shipped bridge is fixed and both scanners evaluate rules. TypeScript is the
concrete trigger to complete this boundary, rather than add a third special path.
Implementation is pending; [the revised proposal](../typescript-foundation-proposal.md)
and [#122](https://github.com/rapiddweller/archkeel/issues/122) track the work.

Prove Python/Dart semantic parity through the port and replacement with another
configured executable. Invalid facts, incompatible profiles and unavailable
tools must fail closed. A language switch in one bridge is not replacement proof.

## Future boundary

HTTP calls and queue publication/consumption are distinct from imports. Future
interaction observers may link explicit API/channel/schema identities across
languages and repositories. Keep intended declarations, source-backed usage
and observed runtime traffic distinct. No such observers or rules are implemented
by this decision; the TypeScript scope only preserves that boundary.
