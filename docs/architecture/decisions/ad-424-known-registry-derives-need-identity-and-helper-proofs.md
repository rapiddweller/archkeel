# AD-424: Known registry derives need identity and helper proofs

Date: 2026-11-13
Status: Accepted
Owner decision: L-117
Issues: #1020, #880

## Context

An unseen attribute or derive expansion has a known source and an unseen target.
The existing pair-gap scope proof keeps its affected rules UNKNOWN.
Unconditional derive gaps also hide useful proof for ordinary registry derives.

## Decision

Keep the gap by default. One typed table models three versioned registry derives:
`serde::Serialize`, `serde::Deserialize` (1.0.229), and `schemars::JsonSchema` (1.2.3).
The model needs both the library and its derive implementation in `Cargo.lock`.
Both must have one crates.io registry identity, the modeled version, and a checksum.
The manifest requirement and lock dependency must agree. Renamed registry dependencies work.
Workspace members, path/git sources, patches, replacements, stale or ambiguous locks,
source configuration files, and identities reached through globs withhold this proof.
The collector starts no Cargo process. It reads these facts through the snapshot.

These derives generate impl code using their own crate, written types, and helper paths.
This is a model of written dependencies, not trait dispatch or runtime behavior (#1004).
The table in `native/rust/src/derive_model.rs` cites the documentation for each helper key.
Read path, type and bound values as Rust syntax, then record their path uses.
This includes bare helper module names. Message text and rename strings are not path uses.
An unknown key, unsupported conditional metadata, macro value or parse failure keeps the gap.

Resolve built-in derives in the workspace, not in the syntax walk.
A block-local glob cannot shadow a module-level derive.
An enum-variant glob imports no macro. A workspace-module glob needs a closed export proof.
Unseen macro output, macro re-exports, external globs and standard-crate aliases keep the gap.
No model changes the gap record or the core's PASS proof.

## Rejected alternatives

- Trust a derive by its final name: a workspace macro can use that name.
- Trust a manifest version without the lock source: a path or patch can replace the code.
- Treat every helper string as a path: rename and message data are not code.
- Drop every glob warning: a glob can import a custom derive macro.
- Infer exports from the absence of records for unseen macro output: that is not a proof.

## Limits and checks

Other versions, helper extensions and function-like expansion remain unmodeled.
`words!` output in the native declarations module still withholds its glob proof.
On main `90a5088fd`, the Python gap count changes from 113 to 116 with this model.
The core changes from 63 PASS, 1 FAIL, 19 UNKNOWN to 0 PASS, 1 FAIL, 82 UNKNOWN.
Without this model, the gap count is 369 and the core has the same statuses.
The three unseen derive targets hold all 63 former PASS rows under AD-418.
Tests: `known_derive_tests.rs`, the compiled core helper-edge probe, and
`test_a_proven_serde_helper_edge_fails_the_forbidden_rule`.
Negative tests retain gaps for workspace macros, globs, renamed path dependencies,
patches, invalid helpers, missing locks and git sources. P8b stays UNKNOWN.
