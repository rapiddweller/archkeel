# AD-446: Script global edges need a closed source publication witness

Status: proposed. Part of #880.

## Decision

Add a small source-only witness, not a runtime or load-order claim.
Require the explicit `classic-browser` host, non-bundler mode and complete compiler settings.
Require global scripts under `moduleDetection: legacy`; reject explicit module suffixes and module syntax as publishers.
Survey the whole snapshot, except `.git`. Every source file must be collected inside the selected roots.
Reject unread files, syntax errors, installed packages, HTML and other unobserved executable inputs.
Only the selected sources, the requested configuration, contract JSON and plain Markdown or text are permitted inputs.
This boundary does not claim to observe scripts injected from outside the snapshot.

Use a closed syntax set in every collected file for this new witness.
Allow comments, empty functions without parameters, empty classes without a base, and plain identifier declarations.
Allow `var`, `let` and `const` with no initializer or a primitive literal initializer.
Allow direct `window.f = literal`, `globalThis.f = literal` and `self.f = literal` expression statements.
The host and property must be plain unshadowed names. Computed properties do not qualify.
Allow direct zero-argument calls through plain name paths as uses, not publications.
Reject all other syntax for this witness throughout the scope, including nonempty function bodies and module files.

Exactly one declaration or host assignment must publish the name in the whole scope.
Any other write, unknown write or ambient declaration prevents the witness.
A publication is unconditional only as a direct statement of the program.
There is no publication inside a condition, block, loop, `try`, function, expression chain or wrapper.
`var` and function declarations publish both a bare name and a host property.
`let`, `const` and class declarations publish a bare global lexical name, never a host property.
A use must be one bare name, or one property of `window`, `globalThis` or `self`.
Do not resolve aliases, members of a published value, or another frame's `parent`, `top`, `opener` or `frames`.
The existing binding analysis excludes local, parameter, import and `declare` shadows from global uses.
An excluded local use has no project-global edge; it does not acquire an artificial global gap.
Standard host globals retain their platform classification, not a project edge from this witness.

The collector emits a binding fact with `script_global`, its module and source evidence.
The import cites that fact through `fact_ids`. No new wire field or PASS maker is added.
The model requires a matching cited publication and target-file evidence for a local global edge.
A saved or wire reply without that proof cannot complete the scope and cannot give PASS.
The existing scope, ownership, profile-limit and PASS makers remain in force.
Load order cannot reverse the dependency: a source use still requires the publisher's definition.
The edge does not prove that a particular execution reaches the publication or succeeds.

## Alternatives and limits

Do not infer a publisher by a name match, a declaration file or a host property of another frame.
Do not extend the old object, wrapper, namespace or vendor analyses with this new witness.
Computed hosts, `Object.assign`, `with`, `eval`, `Function`, sloppy `this` and reassignment prevent the new witness.
Issue #740's assertion, non-null, delete, alias and `Object.defineProperty` writes also prevent this witness.
Unknown source inputs and bundler plugins do not become a closed world by omission.
Every unsupported global use keeps `source_resolution_gap`; no exclusion becomes PASS through this witness.
This deliberately small syntax set can leave the measured corpus unchanged.

## Checks

Collector and release-core tests cover each publication and both dependency directions.
Negative plants cover each boundary, lexical-versus-property access, shadows and source errors.
Model tests remove the citation, binding or target evidence from a resolved global reply.
Mutation checks remove individual guards and require a focused test to fail.
The native self-check and `native/expected-gaps.json` retain their existing pins.
