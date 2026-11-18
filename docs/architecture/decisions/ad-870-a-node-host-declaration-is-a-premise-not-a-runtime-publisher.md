# AD-870 A Node host declaration is a premise, not a runtime publisher

**Decision.** Keep AD-274 for Node ambient values (#832). A project can state its host contract
in a reviewed declaration that both TypeScript and ArchKeel select. Cite that declaration as
the binding evidence. The verdict states the premise: the runtime supplies the declared value.
Neither a package name nor a successful type check establishes that runtime premise.

**Evidence.** In a CommonJS project with `lib: ["ES2022"]`, TypeScript 5.9.3 resolves `process`,
`Buffer`, `setTimeout`, `URL` and `TextEncoder` to declarations in `@types/node` 20.19.43.
It does not resolve them to the ES2022 library. For example, `globals.d.ts:3` declares
`var process: NodeJS.Process`. A Node preload can replace that value without changing any type.

**Missing evidence.** Keep every unresolved import. Report one missing-publication gap per name
in each source file, with every distinct use as evidence. A writer or a preload with its own
diagnosis keeps its evidence. A local import that shadows the name remains an import.

**Rejected.** Do not add a Node name list to the standard library. Do not infer a runtime from
`module: "commonjs"`, an installed types package, or the presence of a lockfile.

**Limit.** The scan does not run TypeScript, execute a preload, or verify the deployment host.
Without a host contract, keep the gap or use a direct import of the Node builtin.

**Tests.** Two reads of `process.env` without a declaration give one gap with both lines.
A scanned declaration gives PASS for the fixture's component rule. A reassignment or a named
preload gives UNKNOWN. An import of a forbidden component under the name `process` gives FAIL.
