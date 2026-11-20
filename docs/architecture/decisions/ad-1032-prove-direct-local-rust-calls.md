# AD-1032 Prove direct local Rust calls

**Decision.** The Rust collector supplies call sites for Explorer. It resolves
simple paths from module functions to unconditional module functions in the
same crate target. It can follow one explicit import of such a function. It
records unresolved calls with their source and the reason for withholding proof.

**Reason.** The parsed source and the module tree can prove these links for
code that compiles. A name match alone could misidentify a call through a
local value or an import that a configuration removes.

**Limits.** Call coverage is partial. Macros can add calls that the collector
cannot read. Method dispatch, callbacks, nested callable bodies, and arbitrary
import chains stay unresolved. Call evidence does not prove runtime execution
or provide a complete inventory for architectural rules.

**Self-scan.** The lead approved 105 collection gaps under AD-672. They record
96 possible trait dispatches, 7 unproved destructor origins, and 2 possible
method dispatches. The self-scan has the same rule statuses and no violations.

**Checks.** Collector tests exercise lexical shadowing and configuration.
The inventory story and the core request story exercise real call evidence
from the release core through Explorer.
