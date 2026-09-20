# AD-55 The decision record splits into one file per decision, indexed in document order

`docs/architecture/archkeel.md` stays the contract's provenance document: its title,
`## Layers`, `## Allowed dependencies` and the `<!-- archkeel-component-graph -->` marker are
untouched, because three `architecture-contract.json` files name it in `provenance` and
`validate` compares its marked Mermaid graph against the observed component edges
(`graph.count`, `graph.drift`); a provenance entry names one existing file, not a directory, so
moving that page was never on the table. Only its `## Decisions` section moves: the 53 numbered
records, [AD-24a](ad-24a-a-module-opens-the-same-way-and-its-interface-is-what.md) and
[AD-24b](ad-24b-observed-is-not-undecided.md) included, 55 in all, now live one per file under
`docs/architecture/decisions/`, and `## Decisions` becomes a short lead-in plus an index table
linking each decision to its file. The index keeps document order, not numeric order, because a
later decision explains an earlier one here on purpose:
[AD-10](ad-10-the-report-draws-component-flow-as-intent-against.md) stands after
[AD-14](ad-14-the-report-headline-follows-its-verdicts-never-the-exit.md), and AD-24b and AD-24a
stand before [AD-24](ad-24-the-report-opens-a-component-without-requiring-a-decision.md);
renumbering the table would have hidden that reading order behind a numeric one nobody chose. A
cross-reference inside a decision's body, "Superseded by AD-33" and the like, becomes a relative
Markdown link to the other file; a mention inside a decision's own heading stays plain text,
since the heading is the record's bold lead-in taken verbatim (its trailing period dropped, the
way a heading drops one), not body prose. The file name itself follows one rule with no
exception: lowercase the title, drop anything that is not a letter, digit or space, collapse
whitespace to `-`, and truncate at a word boundary — never drop a word such as "not" or "never"
to shorten it, since a shorter name that reverses a decision's meaning is worse than a long one.

Reason: the document passed 1,300 lines across 53 decisions, and reading or reviewing one meant
scrolling past the other 52; a diff against one decision touched a file that answered for the
whole architecture, and a reviewer opening it for AD-53 paid the cost of AD-1 through AD-52 too.
Splitting it one file per decision is the move Archkeel's own analyzer already applies to itself
([AD-1](ad-01-analyzer-modules-are-flat-and-singlepurpose.md)): flat, single-purpose units
instead of one file carrying many responsibilities, sized so a reviewer opens exactly the
decision a change is about.

Rejected: renumbering the decisions to run 1..55 in file order, because every commit message,
roadmap row and cross-reference in this repository's own history cites the old numbers, and a
rename would break more links than the split fixes. Grouping decisions by theme (rules,
onboarding, levels, ...) instead of one file each, because a theme boundary is itself a judgment
call this repository has never made, and a decision often serves two themes at once
([AD-42](ad-42-a-requires-entry-may-name-the-modules-it-goes-through-and.md) is both a
`requires` decision and an analyzer-boundary one); one file per decision needs no such call.
Keeping the whole document as it was and only adding anchors, because an anchor still forces the
same 1,300-line file open for a one-decision edit. A slug built from a short, hand-picked list of
significant words, because dropping "not" or "never" from a title to keep it short can flip its
meaning into its opposite, and a file name a reader trusts without opening the file must never do
that; truncating the full title at a word boundary instead costs length, not meaning.

Check: `tests/test_repository_hygiene.py::test_decision_index_matches_decision_files` compares
the index table in `archkeel.md` and the files under `docs/architecture/decisions/` and fails
when either names a decision the other does not; a throwaway script proved the split moved no
text, by reconstructing the original `## Decisions` section from the new files and comparing it
byte for byte to the pre-split document; and `archkeel validate --root . --json` still exits 0,
because the marker, the graph and every provenance path are unchanged.
