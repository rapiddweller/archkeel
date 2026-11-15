# AD-578 Make the remaining self-check calls explicit

**Status.** Proposed. Part of #880.

The native self-check kept 14 module-pair gaps. Write the receiver or method path where the
collector cannot prove it, and give two internal methods names that describe their work. These
changes do not broaden a collector proof or change the called methods. Move `Snapshot::open_root`
beside `Snapshot`, and make the unparse expression module use its dependencies directly. This
removes a real module cycle exposed when the unparse call is proved.

The Dart listing digest now builds the same ordered JSON object without `json!`. A regression
test compares its digest with the earlier macro for multiple inputs and escaped strings. The
snapshot root and collector tests check the moved method and the other unchanged behavior.

The measured native self-check has 84 PASS, 0 FAIL, 0 UNKNOWN, 0 pair gaps and 0 violations.
This is a result for this contract and snapshot, not a claim that the collector has no limits.
The pin and the self-check test record that result. CI checks other platforms.
