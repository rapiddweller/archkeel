# AD-1000 TypeScript records the written anonymous default function

**Decision.** The native TypeScript collector records a direct anonymous default function as a public
function at `<module>.default`. Its evidence points to the written function. The existing symbol
record carries the identity. A named default function keeps its written name.

The record does not add a lexical binding, a resolved import route, or a new scope. It does not
prove a complete symbol or relationship inventory. A module with a competing export route that
the collector cannot distinguish does not get the new identity.

**Reason.** The compiler exposes `default` for `export default function () {}`. A closed UML scope
can FAIL when it omits this written function, even when the collector cannot prove the full inventory.
An explicit UML entity can match the function without a claim about how a caller reaches it.

**Rejected.** A source coverage gap: the file is read, and the written declaration provides positive
evidence. Treating the export as a local name: a caller can shadow its import, and the declaration
does not bind `default` inside the module.

**Limit.** This does not cover default assignments, re-exports, other anonymous values, declaration
files, or JavaScript inputs. The UML fixture and its `String` relationship stay unchanged.

**Tests.** `native/typescript/src/symbols_tests.rs` checks the export record and the named and
private controls. `native/typescript/src/site_records_tests.rs` checks that the fact does not resolve
default-import calls. `tests/test_cli_core_uml_symbols.py` checks the UML rule and source evidence.
