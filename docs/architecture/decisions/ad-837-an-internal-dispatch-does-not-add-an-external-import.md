# AD-837 An internal dispatch does not add an external import

**Status.** Accepted.

**Reason.** The Rust collector leaves a pair gap when a call can run code in another module
(AD-804, AD-806). The target module can import an external package. Running its code does not
import that package into the caller.

**Decision.** Mark a linked Rust pair gap from the dispatch flow as a dispatch gap. Keep the
existing gap when another cause has already recorded the pair. Those causes can leave an import
or re-export unknown. A gap with an end outside the reply keeps its previous effect.

The external rules can judge a known pair with only the dispatch cause. The complete external
scope rule reads no internal edge. An external dependency scope rule still reads a dispatch whose
internal target matches its dependency selector. The other rules read the same pair gaps as before.

**Compatibility.** The linked reply carries the dispatch marker. The compressed reply keeps the
protocol 11 record and the old conservative rule result, as for publication routes in AD-604.

**Rejected.** Read the reason text to classify the gap. The text is for the reader and cannot
prove the scope of a gap. Change the protocol 11 record. Its wire shape is frozen.

**Tests.** The former UNKNOWN package rules pass when the only gap is an internal dispatch.
A matching internal selector, an opaque macro with an external path, and a private impl in a
foreign type all keep a non-PASS result. A direct external path gives FAIL. The wire round trip
retains the untyped gap, and an out-of-scan target keeps its effect.
