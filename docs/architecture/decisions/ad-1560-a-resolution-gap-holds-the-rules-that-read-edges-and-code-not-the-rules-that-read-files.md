# AD-1560 A resolution gap holds the rules that read edges and code, not the rules that read files

**Status.** Accepted. Part of #1919 (plan row `STUDIO-ASSIGNMENT-COMPLETE`). It extends [AD-564](ad-564-a-gap-states-its-effect-and-holds-only-the-rules-that-read-it.md) and [AD-634](ad-634-each-collector-states-the-effect-of-its-gaps.md).

**Reason.** On main the Studio part (TypeScript) was UNKNOWN for `STUDIO-ASSIGNMENT-COMPLETE`. The 184 coverage gaps of the part are `source_resolution_gap` entries (script globals that a file outside the scan can replace, preloads). None states an effect, so each one left the whole scope unknown, also the files and their owners. `complete_assignment` reads only the files of the scan and the components of the contract (AD-564 D1).

**Decision.**
1. A gap of kind `source_resolution_gap` that states no effect and is no pair gap has the effect `every_module`: the edges and the code of each module are unknown, and `L` (the file, the name and the place in the layout) is known. The kind decides this, never a reason text. `gap_class::effect_of` is the one place.
2. So such a gap holds each rule that reads an edge or code, as before. It no longer holds a rule that reads only `L`: `root_layout` and `complete_assignment`.
3. An unresolved import that no gap names (`Incomplete::UnknownImports`) is the same class: an unknown edge. It holds no rule that reads only `L` either (`gap_effects::reads_layout_only`, derived from the read set, not a list of kinds). Such a rule reads the scope state without that one cause (`proof::layout_state`); each other cause of the state (an unknown Git head, the runtime, the producer, a rule that selects no module, a split owner) still holds it (review of #2250).
4. An unresolved import that such a gap cites is now named by that gap, because the effect `every_module` leaves the code of the source unknown (AD-634 item 2).
5. Unchanged: a `collection_gap` (a file that is unread, unparsed or not in the reply, a syntax error), a gap of another kind, a pair gap and a gap with a stated effect. A file that no component owns still fails `complete_assignment`. A gap with a `layout` effect still holds it.

**Why it is sound.** A collector writes the files, the module names and the place in the layout from the file tree before it resolves any import. A resolution gap says that an edge or a signature is unproven. It adds no file and removes none. Each collector reports a file that it cannot read or parse as a `collection_gap`, so the file problems stay in the class that holds every rule. A resolution gap that states no effect can still change the code of any module, so every rule that reads code or edges keeps it.

**Counter-examples (tests).** `tests/test_cli_gap_effects_languages.py`: an unresolved import beside a component file gives `ASSIGN` PASS and `A-NO-B` UNKNOWN. A file that no component owns (also a generated declaration file) gives FAIL. A syntax error and an unreadable file give UNKNOWN. A generated file of a component stays judged. The unit tests of `gap_class.rs` and `imports.rs` pin the class, the pair form, the stated effect and a collection gap of the same shape.

**Measured.** Studio part alone: `STUDIO-ASSIGNMENT-COMPLETE` UNKNOWN to PASS; `STUDIO-COMPLETE-REQUIRES` stays UNKNOWN (184 gaps leave the code of every module unknown). System run: the same, no other verdict changes. CE and EE copies: no verdict changes (the Python collector states an effect for each of its resolution gaps; all `*-ASSIGNMENT` rules were PASS).

**Not done.** A resolution gap that is meant to hold the files of a collector must not use the kind `source_resolution_gap`: it must be a `collection_gap`, or state a `layout` effect.
