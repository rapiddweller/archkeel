# AD-1042 Facts skip marks use Option and Nullable methods, not a trait

**Decision.** The crate `archkeel-facts` has no private trait `Present` and no function
`omitted`. The file `native/facts/src/skip.rs` is deleted. In `facts_data!`, the mark `skip`
writes `skip_serializing_if = "Option::is_none"` and is for a field of type `Option<_>`. The new
mark `absent` writes `skip_serializing_if = "crate::nullable::Nullable::is_absent"` and is for a
field of type `Nullable<_>`. A wrong mark does not compile, because each method takes one type.
The test `native/facts/src/skip_wire_tests.rs` pins the wire keys.

**Reason.** `Present` had two impls, one for `Option<T>` and one for `Nullable<T>`. A trait impl
makes each module that reaches `facts.skip` a possible runner of that impl. Rule
NATIVE-REQUIRES-COMPLETE then holds the module pair as UNKNOWN. The `[skip]` fields are in many
modules, so this made 330 holding pairs. The two methods are inherent and name their type, so the
collector proves them.

**Effect.** The wire output does not change. `None` and `Absent` write no key. `Null` and
`Value` keep their key. On the native self-scan (`native/archkeel.toml`) the collection gaps
fall from 18,393 to 18,006 and the NATIVE-REQUIRES-COMPLETE holds fall from 11,997 to 11,665.
The verdicts do not change: 89 PASS and 3 UNKNOWN.

**Limits.** This change does not change a verdict. Other trait impls in the workspace still make
the same kind of hold. The `absent` mark adds one word to the macro vocabulary.
