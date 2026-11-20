# AD-932: Rust dispatch does not hide a written name route

**Reason.** Store had 41 pairs holding its source-name rule. Twenty cited possible
destructors at `snapshot/src/test_tree.rs:43` or `snapshot/src/work.rs:92`. The other
21 cited a receiver or an associated path. No pair cited a glob or a re-export as
its blocking cause. An unknown value origin is not an unknown written name.

**Decision.** The Rust collector proves that a directly read dot call or possible
destructor adds no written route to its receiver type. The worker transfers this
proof with the gap ID. An unread path or glob is not such a proof. If any candidate
for a deduplicated pair can hide a route, the pair keeps that doubt in either order.
A separate site beside a known edge keeps its own proof or doubt.

Only a source-name rule reads this proof. The constraint still reads named uses
and unresolved paths. The worker and the model leave the ordinary dispatch and
interface scope data intact. The public facts schema does not change.

**Store.** Use closures on the values of the known containers where a qualified
method path made dispatch look like another name route. This includes
`Section::name`, `Record::invariants`, and `<[String]>::is_empty`. The type imports
and the checks of the values remain.

**Model.** Use the typed analysis capabilities from the validated Store input.
Facts owns the fixed mapping for the profile. The model reads the values, including
the layout, symbol support, and import target marks. It does not choose them from
the profile. Producer trust and the checks of the reply stay separate.

**Limit.** The proof does not resolve a receiver, a destructor, a qualified path,
or a macro expansion. It does not discharge an unread source module. An archive
cannot supply the private proof.

**Check.** Rust controls cover inferred receivers, an erased destructor, a
re-exported alias, a glob, a type argument, a pattern, and an unread route beside
an execution cause. The duplicate-pair test reverses the order of the causes.

**Result.** On base `d2947322c`, Store goes from 41 pairs and UNKNOWN to
0 and PASS. Eval goes from 102 to 1, Report from 126 to 2, Core from 247 to
9, and Model from 439 to 1. Those four stay UNKNOWN. The result is 83 PASS,
0 FAIL, and 9 UNKNOWN. The raw inventory grows from 23,015 to 23,017 gaps.
The new capability route adds five possible impl edges. Three prior gap
records no longer apply.
