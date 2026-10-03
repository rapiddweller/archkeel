# AD-150 TypeScript imports use a pinned npm collector

The external npm package uses TypeScript Compiler API 5.9.3 for parsing and
resolution. Its four source modules emit facts; Core retains policy and verdicts.
`package.json` owns supported Node versions. Analysis installs nothing and never
executes project code or scripts.

Selected source and resolver inputs bind exact bytes to the revision. Explicit
JavaScript runtime closure remains distinct from TypeScript and declarations.
Computed, indirect and incomplete imports stay UNKNOWN. Local value aliases and
relative package-directory targets retain compiler source evidence; Node runtime
conditions and package metadata targets remain unproved.
Their runtime_file stays null and coverage UNKNOWN; unread runtime bytes are
not claimed in the source digest. Type-only aliases retain compiler resolution. Unavailable call, type,
construct and private-use measurements stay null.

The package has its own source contract and a locked package verification Make
entry point. CI and publication require separate proof. See [the decision](../typescript-foundation-proposal.md).
