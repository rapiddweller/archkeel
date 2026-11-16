# AD-606 The report page holds the 4.0.1 Explorer with the 5.0 design tokens

**Status.** Proposed. Part of #880. It replaces the picture of AD-594 (points 5 to 7) and points 2
and 6 of AD-496. AD-594 points 1 to 4 stay: the three views and the declared structure in `topology`.

**Decision.**
1. The architecture section of the report page is the ArchQ Explorer of 4.0.1: As-Is, Target and
   Diff, the breadcrumb, a double click to open a component, search, perspectives, the panel of the
   selection and fullscreen. Its scripts are the files of tag `4.0.1` in
   `native/report/assets/explorer/`. They change only where the 5.0 data or design differs (points 4 to 6).
2. The page writes one JSON block (`flow-data`) in the payload shape that the 4.0.1 Explorer reads.
   One adapter in the report crate (`html_atlas*.rs`) maps the frame to it: the components and
   their parents, the modules and their owners, the imports between modules, the declared
   requirements, the violated places and the gaps. A `<` in the data is written as `<`.
3. The page decides no verdict. A component is FAIL when a violated place names a module inside it,
   and UNKNOWN when a gap or a held pair names a module inside it. An edge is FAIL when a rule that
   fails cites it (`topology.edges[*].rules`). Diff compares two lists of the frame at each level:
   observed imports between two children without a declared requirement are "undeclared", and
   declared requirements without an observed import are "allowed, unused". The lede counts the
   same component statuses as the Explorer.
4. A contract whose top components all name a layer of its first `layer_order` opens on its
   layers: one box for each layer, with its components inside. Else it opens on its top components.
   The start view is always the whole run, never a part of it.
5. The topology states the language of each module (the collector of its reply) and the
   responsibilities of each component. The Explorer opens with the perspective "Language": each box
   names its language, and the bar of the perspective lists each language with its count.
6. Every colour, font, radius and space of the Explorer is a token of `tokens.css`; the rules of
   `explorer.css` read the tokens directly and define none. `explorer-theme.css` only places the
   Explorer in the page: the width of the report column, a height of 680 px and a narrower panel.
   Fullscreen uses the whole window; "Back to report" and Esc return and keep the level and the view.
7. The fact sheet shows what the contract states: the responsibilities, the forbidden
   responsibilities ("Not responsible for"), the public surface ("Provides"), the planned surface,
   and each `requires` entry with its rationale and its `through` ports. Each port is a declared
   boundary permission; the frame names no applied one. Diff draws an edge red when it is
   undeclared or when a failing rule cites it; a box with a violated place has the FAIL border, a
   box that a gap holds the UNKNOWN border. A run of one collector names that limit in the lede and
   in the legend. Each violated place is a full block.
8. In the report the Explorer starts with the panel closed, so that the diagram has the whole
   width; a click on a box opens the panel.
9. Without `--root`, a configuration outside the repository of the working directory names its own
   root: the Git root above the file. A refused collection states its own refusal, not a missing
   topology.
10. The policy admits each script by its SHA-256: the theme switch and the eight Explorer scripts.
   The page still loads no resource (`default-src 'none'`).

**Reason.** The owner rejected the static picture: a reader needs the structure, a drill-down to the
place of a violation and the three views. The 4.0.1 Explorer gives them and is proven. One adapter
keeps the frame the only source.

**Rejected.** A new viewer: the 4.0.1 Explorer exists and is the bar. Copying the 4.0.1 page:
it has its own header, verdict and colours. Layouts in Rust: ELK in the page lays out each level.

**Limits.** The page is at most 3,500,000 bytes on the core self run (about 3,000,000 today; ELK is
1.6 MB). The frame names no symbol count; a module says "no symbol count in this run". A Cargo
manifest is a module of the reply until the collector states the kind of each file. One run has one collector reply, so the
self report names one language (Rust); a report of the whole system with its Python and Rust parts
needs the system contract (AD-522). The links of 4.0.1 to its JSON file and its detail page point to
the steps on this page. The scripts keep about 40 `innerHTML` sinks of 4.0.1; the browser self-check
shows them, and a later change removes them.

**Tests.** `native/report/src/html_tests.rs` (the data block, the edges of a level, hostile names,
the row tracks of each evidence path), `native/report/src/html_explorer_tests.rs` (no colour of its
own in `report.css` and in each Explorer asset, no redefined token), `tests/test_cli_report_page.py`
(each script admitted by its hash, no load, the budget, the counts of the line and of the data).
