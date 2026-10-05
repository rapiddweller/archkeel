# AD-192 UML details separate label and identity

The shared UML inspector uses the card label as its heading. The full qualified
name remains directly below it, with line breaks allowed after namespace separators.
Long paths no longer split a short member name across heading lines.
Source excerpts wrap within the inspector; their text and indentation are preserved.

Entity IDs, qualified names, navigation and report data are unchanged.
Relationship headings keep their existing meaning.

Proof: As-Is, Target and Diff browser tests check the short heading, complete
identity, namespace break points and unchanged report payload.
