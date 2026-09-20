# AD-59 A type crossing many component boundaries is a review claim, not a verdict

`cross-component type fan-in` is the fifth Class D review claim (AD-26): its signals are the
`symbols` and `imports` sections, `imports` for which function or method a cross-component call
reaches, `symbols` for that function's own parameter and return annotations. The derivation in
`ir.type_fanin` groups every crossing function once per ordered component pair it is called
across, however many import sites name it, collects the raw annotation string at every parameter
and return position, and names every annotation string passed across two or more distinct
component pairs, most-crossed first; a type crossing exactly one pair is ordinary parameter
passing and stays uncounted. A missing `symbols` or `imports` section reports `UNKNOWN` and no
candidates, the way every claim without its signal does (AD-26).

Reason: issue #9 asked for a claim naming which types are passed across the most component
boundaries, because a broad context object acting as a service locator would show up as one name
crossing unusually many of them. The claim needed no new signal: `symbols` already carries a
function's own parameter and return annotations, `imports` already carries which cross-component
call reaches which function, and `ir.interfaces.component_owners`/`owner_of` already map a module
to its owning component. On the shop sample the claim names `Order` and `str`, each crossing two
component pairs. On Archkeel itself it names 23 candidates; the widest are `str`, `bool`, `bytes`
and `object`, all builtins or `ir.codec`'s own untyped-JSON boundary, and `Observation` and
`RunResult` follow at three pairs each: Archkeel's shared IR model crossing widely is exactly what
a codebase built around one shared evidence model looks like, not a service-locator context
smuggled through a facade. That reading is the architect's to make, never this claim's, which is
why a high count is reported and never gated on.

Rejected: reusing `ir.interfaces.interface_edges`'s own `InterfaceName` values instead of reading
`symbols` and `imports` directly, because that type formats a parameter as `"name: Type"` for the
report table it was built for, and unpicking the type back out of that string on every read would
be a second, string-shaped derivation layered over the first; the raw parameter and return
annotations `symbols` already carries need no such round trip. Counting a crossing once per import
site instead of once per (source, target, function) triple, because a function reached by five
import sites from the same component would then report five crossings of one pair, inflating the
count with how many places call it rather than how many components it reaches. A floor of one
crossing instead of two, because every cross-component call already produces exactly one, and
listing that unfiltered would name every ordinary parameter in the report as a "crossing".

Limit: the annotation is the raw string a function declares, not a resolved type, so an `Order`
from one module and an unrelated `Order` from another module are the same candidate; this is the
same name-resolution question AD-58 leaves unfinished for `boundary_types`, and the claim inherits
it rather than duplicating a second, partial attempt at resolving it. A call reached only through
a re-export chain the scan cannot expand is invisible, the way `interface_boundary`'s own blind
spot is. `ANALYZER_VERSION` is unchanged: the claim is a pure `ir` derivation over sections the
analyzer already produced, so no contract yields a new record. Check:
`tests/test_type_fanin.py::test_the_claim_is_unknown_without_the_imports_signal`,
`tests/test_type_fanin.py::test_the_claim_is_unknown_without_the_symbols_signal`,
`tests/test_type_fanin.py::test_a_type_crossing_two_component_pairs_is_named`,
`tests/test_type_fanin.py::test_archkeel_itself_names_its_own_shared_ir_types`, and the demo row
`class-d-type-fanin` in `docs/architecture-demo.md`.
