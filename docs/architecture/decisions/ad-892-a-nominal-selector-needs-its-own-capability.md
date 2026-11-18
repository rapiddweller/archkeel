# AD-892 A nominal selector needs its own capability

**Status.** Proposed. Part of #880.

**Reason.** The Model used the Python profile as evidence that a collector reports
nominal construct selectors. The current Python collector does not report them.
The TypeScript collector reports literal comparisons but not nominal selectors.
The Rust and Dart collectors report neither. The Store still refuses selector records.

**Decision.** Read the existing construct capability for the selector record kind.
Require `Supported` before the Model can prove a selector rule. Missing, partial,
unsupported, and construct-decision-only facts cannot grant this proof.
The rule still needs complete source coverage and an observed selected subject.
A known violation still fails even when the receipt for absence is incomplete.

**Rejected.** Do not infer complete observation from the language, from a
literal comparison capability, or from one selector record.

**Limit.** The four collectors and the Store keep their current behavior and
wire format. This change does not add nominal selectors to a collector or
teach the Store to validate them. The Model's profile dependency for this
decision is gone. Other unresolved dependencies still hold the neutrality rule.

**Tests.** Model tests cover absent and partial support, explicit supported
facts independent of profile, and a known violation with incomplete support.
The Python CLI test checks that a nominal selector rule is UNKNOWN.
