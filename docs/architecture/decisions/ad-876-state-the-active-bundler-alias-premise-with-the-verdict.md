# AD-876 State the active bundler alias premise with the verdict

**Decision.** When AD-260 bundler mode is active, state that the bundler's aliases match
tsconfig `paths` in the verdict. Keep the host premise and any generated-copy premise.
Use the mode the collector accepted, not the requested option alone.

**Reason.** For #828, TypeScript 5.9.3 resolves `@b/b` through `paths` to `src/b/b.ts`.
The emitted JavaScript still imports `@b/b`. Node without an alias loader cannot find it.
A compiler target proves the source edge, not the runtime mapping.

**Rejected.** Do not infer the bundler from the spelling of the import or from the tsconfig.
The project must set `[scan] bundler = true` and use compatible compiler settings.

**Tests.** The forbidden compiler edge gives FAIL with and without the opt-in. The runtime
gap stays without the opt-in, with an incompatible resolver, or for a `baseUrl`-only match.
Only active bundler mode adds the alias premise, including when a generated copy is present.

**Limit.** The scan does not execute a bundler or read its alias configuration.
