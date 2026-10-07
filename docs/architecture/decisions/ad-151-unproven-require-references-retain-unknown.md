# AD-151 Unproven require references retain UNKNOWN

Resolve direct literal CommonJS `require` calls, but retain UNKNOWN for loader
references that can escape through aliases, members, containers or exports.
A call-only guard would falsely claim complete dependency coverage.

Known Node namespace references survive erased TypeScript wrappers. Proven
members and aliases remain supported; type-only references introduce no value gap.
Unproved re-exports and runtime escapes need further binding and flow proof.
Core retains coverage gaps and unavailable measurements without asserting absence.

[Historical collector proof](https://github.com/rapiddweller/archkeel/blob/4e215679be7ae063ab1de7da189e4565e7851727/packages/typescript-adapter/test/adapter.test.mjs).
