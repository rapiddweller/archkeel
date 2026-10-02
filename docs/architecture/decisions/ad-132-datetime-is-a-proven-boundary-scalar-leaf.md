# AD-132 Datetime is a proven boundary scalar leaf

A published owned DTO can carry `datetime.datetime` without leaving that field UNKNOWN (#205).
The shared annotation reader accepts exactly this stdlib origin as a scalar leaf. It follows
an explicit class import, its alias, or a single module member through the existing import
proof. Mappings reuse the same binding proof and remain broad boundary types (AD-123).

An import must have one stable binding. Module imports now retain the same uniqueness fact as
symbol imports. Rebinding, deletion, conditional replacement, shadowing and star imports cannot
prove this leaf. Unknown external classes and other datetime types remain UNKNOWN; `object`
remains a violation. No class is accepted from its spelling alone. Forward references and
unproven re-export routes retain their existing limits.

A blanket stdlib/class exemption would hide unresolved models. A new type resolver would
repeat the existing trust boundary; both were rejected. The leaf decision is shared by
boundary and facade checks, JSON and report evidence. Analyzer version advances to 0.64.0.

`tests/test_boundary_types_datetime.py` covers import forms and negative bindings. The datetime,
external and object-field catalog demos retain unrelated report UNKNOWNs.
