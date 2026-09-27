# AD-120: Direct publication crosses only declared ancestors

Status: accepted. Issue: #193.

A child may directly implement its parent's public API. A real outside consumer
then proves local use without an extra wrapper or sibling caller.

Count the incoming module or symbol only when every ancestor boundary it crosses
publishes that route. Stop at the common ancestor containing the caller. Reuse
facade membership and unique ownership checks; private outer boundaries still
block this evidence. Publication alone, without an observed consumer, is not use.

Existing local and re-export evidence stays unchanged. This corrects API lifecycle
diagnostics, including planned-entry promotion; it grants no dependency permission
and removes no rule violation. Class-method return exposure remains outside this fix.

Proof: `tests/test_inside_direct_parent_publication.py` covers direct publication
and rejected private, unused and mismatched routes. The demo catalog pairs
`validation-inside-direct-publication` with its `-private-parent` negative case.
