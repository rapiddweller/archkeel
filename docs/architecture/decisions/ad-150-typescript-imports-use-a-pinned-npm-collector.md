# AD-150 (historical): TypeScript imports use a pinned npm collector

Superseded by [AD-210](ad-210-typescript-frontend-ships-in-the-package.md). This record
preserves the original decision and its limits; the removed collector source is pinned at
[`4e215679`](https://github.com/rapiddweller/archkeel/tree/4e215679be7ae063ab1de7da189e4565e7851727/packages/typescript-adapter).

Use a pinned npm collector using the TypeScript Compiler API.
It emits facts; Core owns verdicts. Analysis installs nothing and executes
no project code or scripts. Digests bind source and resolver bytes.

Compiler resolution cannot prove Node runtime lookup. Non-explicit CommonJS targets
and missing explicit JavaScript files remain UNKNOWN. Unproved value targets keep
compiler evidence without a runtime file or unread-byte claim.
Unavailable measurements stay null; publication requires separate proof.

[Historical collector proof](https://github.com/rapiddweller/archkeel/blob/4e215679be7ae063ab1de7da189e4565e7851727/packages/typescript-adapter/test/adapter.test.mjs).
