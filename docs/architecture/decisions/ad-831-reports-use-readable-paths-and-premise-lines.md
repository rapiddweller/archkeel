# AD-831 Reports use readable paths and premise lines

## Decision

Show absolute paths in text headers for projects outside the current folder.
Keep relative paths for projects in or below the current folder.
Preserve the spelling of an explicit absolute root in the display.
This replaces the display rule of AD-826.

Join collector assumptions once in part order. Remove trailing full stops
from assumptions that precede a separator.
Use singular wording when exactly one rule rests on a premise.

## Reason

Parent-folder paths can obscure the scanned project.
Each assumed rule must remain visible in the verdict.

## Alternative

Keep all paths absolute. This adds noise to scans from the project folder.

## Check

The project-root test checks absolute and relative paths.
System, HTML, and CLI text tests check assumption punctuation and rule counts.
