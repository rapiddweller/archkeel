# AD-971 Prove an import target from an adjacent local literal

**Decision.** Reuse the literal import path for one local name. A top-level
function after a direct `import importlib` can assign an absolute dotted string
to one local name and return `importlib.import_module` called with that name.
These must be the only two statements in the function body.

**Reason.** The assignment always runs before the call. No statement can
change the local name between them. Read the AST, not the source excerpt.
Reuse the loader binding check and reject visible loader writes or a file
that can shadow `importlib`.

**Alternatives.** A binder count alone does not show which assignment reaches
the call. A general control-flow analysis is not needed for this case.

**Limit.** This does not follow closures, conditional assignments, loader
aliases or calls with intervening statements. It changes no contract,
premise or wire format. It does not prove receiver ownership (#613).

**Tests.** Native survey tests check a multiline literal assignment and require
a dynamic-import gap for unproven bindings, paths and loader writes.
