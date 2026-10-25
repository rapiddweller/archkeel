# AD-265 `archkeel guide` writes a readable guide from the contract

**Decision.**
- `archkeel guide` reads the contract and writes Markdown, by default to
  `docs/architecture/contract-guide.md`. It needs no source scan and never changes the contract.
  `--check` writes nothing and exits 1 when the file on disk differs, so CI can keep it fresh.
- The output is a pure function of the contract: no dates, no hashes of the repository, stable order.
  The same contract gives the same bytes.
- It is a separate file from `docs/architecture/architecture.md`. That file is written once by
  `init` and edited by people; the guide is regenerated and is never edited.
- With no contract, `archkeel guide` exits 2 and says what to do first: `archkeel init`. It
  does not invent a guide. `init` writes the guide as its last step (AD-266), so a first-time
  user gets a readable file from the first command.
- Sections, in order: *At a glance* (counts, and what is missing); *Components* (ownership and
  responsibility); *Public interfaces*; *Rules* (grouped by kind, one explanation per kind, then
  one row per rule: id, scope, who decided, the contract's own rationale); *Decided and open*;
  *Review items*.
- The plain-language text for each of the 15 rule kinds is written once, in a table in the
  code. A kind that has no text is listed as "no explanation yet", with its raw declaration
  named, and is never dropped.
- *Decided and open* separates what the file states from what it leaves open: no `requires`
  and no `complete_requires` means dependency permissions are incomplete, and the guide says so.
  It never turns an observed import into a permission.
- A target dependency graph (Mermaid) is drawn only when `requires` entries exist, from the same
  pairs `validate` checks against `<!-- archkeel-component-graph -->`, and is labelled "declared".
- Recorded authorship is shown as recorded ("decided by: agent"), never as verified approval.
- Large contracts: a table of more than 40 rows, and a rule kind with more than 10 rules,
  is wrapped in `<details>` with the first 10 visible. Counts stay in the heading, so the
  page is readable at 12 components and at 140.

**Reason.** #679. A new user cannot read `architecture-contract.json` without knowing the
schema. The guide that Tung wrote by hand for fastmcp (12 components, 3 rules) shows the
target. ArchKeel's own contract has 44 components and 276 rules, 41 of them
`forbidden_construct`; the guide has to stay short there too.

**Rejected.**
- Extending `architecture.md`: people edit it, so regenerating would lose their words.
- A free-text "repository context" paragraph: it is not in the contract, so it would be invented.
- Dates in the header: they make the file differ on every run.
- Explaining rules with an LLM: not reproducible, and not checkable.

**Slices.** 1: the command and all sections except the graph. 2: the declared graph and `--check`.

**Check.**
- Tung's fastmcp contract gives a guide that says dependency permissions are not declared,
  lists the 3 rules with their rationale, and draws no dependency graph.
- A contract with `requires` entries gets the declared graph, and its pairs equal the ones
  `validate` accepts.
- Two runs give identical bytes; reordering JSON keys in the contract does not change the output.
- ArchKeel's own contract gives a guide where `forbidden_construct` shows 10 rules and a `<details>` block for the rest.
- A rule of a kind without text is listed, not skipped.
- `--check` exits 1 after a contract edit and 0 after regenerating.
