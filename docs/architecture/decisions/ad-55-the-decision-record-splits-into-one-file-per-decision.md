# AD-55 The decision record splits into one file per decision, indexed in document order

Keep `docs/architecture/archkeel.md` as provenance, including its title, Layers,
Allowed dependencies and `<!-- archkeel-component-graph -->`. Three contracts
reference that file; validation checks its graph. Move only Decisions into one
file per record under `docs/architecture/decisions/`, with an index at the old location.

Retain IDs and document order: [AD-10](ad-10-the-report-draws-component-flow-as-intent-against.md)
follows [AD-14](ad-14-the-report-headline-follows-its-verdicts-never-the-exit.md), and
[AD-24b](ad-24b-observed-is-not-undecided.md) and [AD-24a](ad-24a-a-module-opens-the-same-way-and-its-interface-is-what.md)
precede [AD-24](ad-24-the-report-opens-a-component-without-requiring-a-decision.md).
Body references become relative links; heading text stays unchanged apart from
its original trailing period.

Slugs lowercase the title, remove nonletters/digits/spaces, collapse whitespace
to hyphens and truncate at a word boundary. Do not hand-pick words or drop `not`
and `never`, which could reverse meaning.

The original 1,300-line page had 53 numbered records plus 24a/b. Separate files
reduce review scope, following [AD-1](ad-01-analyzer-modules-are-flat-and-singlepurpose.md).
Renumbering would break historical references; themed groups require ambiguous
ownership choices ([AD-42](ad-42-a-requires-entry-may-name-the-modules-it-goes-through-and.md));
anchors still open the whole page.

Checks: `test_decision_index_matches_decision_files` compares index and files.
A reconstruction script proved the original split byte-identical; validation
still exited 0 with unchanged provenance and graph.
