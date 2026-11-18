# AD-888 Check the runtime against the reported target

**Status.** Proposed. Part of #880.

**Reason.** The Model asks the language profile whether a missing project runtime requirement is
acceptable. The linked collector already reports how it selected its target. The Python collector
reports a configured or default target even when the project declares no requirement.

**Decision.** Use that existing target evidence in the Model. Accept the missing requirement only
when these conditions hold:

- The host verified the producer and the graph bound it to the reply.
- The reply carries the live collector's profile statements.
- The producer reports a numeric target selected from configuration or its default.
- The metadata or the requirement is absent, and the reply contains no requirement text.

A declared requirement still goes through the numeric range check. Invalid metadata, an unread
requirement and a legacy interpreter selection do not grant the exception. The Rust, Dart and
TypeScript collectors report their native runtime requirement and no target selection.

**Wire and offline replies.** Keep the existing protocol and the `target_source` field. A decoded
reply retains that field but cannot acquire the live statements from its bytes. The field alone
does not authorize the exception.

**Rejected.** A second flag would repeat the target selection that the collector already reports.
A profile-dependent accessor would hide the same language decision behind another name.

**Limit.** This removes the Model's profile query for this runtime decision. It does not prove the
whole `NATIVE-NEUTRAL-MODEL-NO-PROFILE` rule or release its unrelated pair gaps.

**Tests.** The Model tests cover a valid live target, absent evidence, an external or wrong
producer, serialized replies, and contradictory or invalid runtime data. The CLI tests cover
default and configured Python targets, absent metadata, invalid and incompatible requirements.
