# AD-190 Member previews remain readable

One long classifier name widened every card in its scope. The own Target's
25-node overview then shrank headings below the existing 11-pixel acceptance
limit. Keep the existing 200-pixel card width and wrap long names horizontally.
Remove the width expansion instead of adding another layout setting.
Identifier wrapping prefers underscores and camel-case word boundaries. Small
call graphs retain complete helper names in at most two horizontal lines; their
text must still pass the existing 11-pixel readability limit.

Fit still shows a collapsed overview. Expanded attributes and operations use at
least their native text size, like focused neighborhoods. Large expanded scopes
remain pannable; shrinking every member onto one screen makes the UML unreadable.
Existing hidden scrollbar tracks and navigation controls remain in use.

The own Target heading measured 12.8 pixels with compact cards. Collapsed and
expanded Target routes passed the overlap check in this scope. This does not
certify every complete source graph.

Proof: `test_member_previews_do_not_squeeze_the_overview_or_change_its_evidence`
checks the same identities, full details, keyboard toggling and member text size
in As-Is, Target and Diff.
