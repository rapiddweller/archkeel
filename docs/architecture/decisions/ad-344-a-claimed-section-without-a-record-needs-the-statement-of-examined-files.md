# AD-344 A claimed section without a record needs the statement of examined files

**Decision.** A collector that claims `calls`, `references`, `constructs` or `unknowns` and
sends no record for it must also send `capabilities.examined`. For each such section it holds
the SHA-256 of the sorted, newline-joined paths of the files that the collector examined. The
host compares it with the digest of the paths of the parsed files in the same reply. A missing
or different digest rejects the reply. The scan then ends with exit 2 and UNKNOWN, as for a
dropped section. This only makes verdicts more cautious. Epic #880, task L2.

**Problem.** A reply that claimed `calls`, `references` or `constructs` and held no record gave
`complete=PASS`, exit 0 and the same diagnostics. A reply that emptied `unknowns` did the same.
The host could not tell "the source has no call" from "the collector did not look". Today only the
4.2 gap of the native TypeScript collector keeps its scans incomplete. PR 4.3a-5 removes the gap.

**Rule.**
1. The field is optional on the wire. A reply without it states nothing. `encode_examined` writes
   it only when a section has a statement, so a reply with records everywhere stays unchanged.
2. `check_examined` (in `ir/claimed_sections.py`) runs in `validated_facts`, the one place where
   the host validates collector facts. It raises for: a statement for a section that is not
   claimed or not checked; a digest that differs from the parsed files; a checked, claimed
   section with no record and no statement while the reply has a parsed file.
3. A reply with no parsed file needs no statement: no file means nothing to examine.
4. The Python, Dart and TypeScript collectors call `states_examined` on the facts that `collect`
   returns. The native encoder (`native/wire/src/reply.rs`) states it with the same digest.
5. The module joins the component `facts-codec`. `ad-344-amendment.json` records that widening.
6. The schema `schema/source-facts.schema.json` allows the field. The TypeScript golden replies
   are recorded again; the only change in each is `capabilities.examined` (AD-343).

**Verdict evidence.** Each check ran with the rule and with `check_examined` replaced by a no-op.
- 57 catalog cases (53 TypeScript variants, 4 fixtures), default collector: 0 verdicts, rule
  statuses, diagnostics or artifacts differ. 28 PASS and 29 UNKNOWN in both runs.
- The TypeScript golden replies: the section records are equal; `capabilities.examined` is the only
  new field (`h-typescript`: `constructs`, `unknowns`).
- False-PASS probe in `tests/test_collector_claimed_sections.py`: a claimed section with zero
  records and no statement was PASS before the change for `calls`, `references`, `constructs`
  and `unknowns`. It is not PASS now. A statement for a missing file or for an extra file is not PASS.

**Rejected.**
- **Empty is UNKNOWN.** A project with no call is legal, and the rule would change real verdicts.
- **A list of paths.** It grows with the number of files for each section. A digest is constant.
- **A statement for every section.** It changes every golden reply. A section with records is
  not silent, so the statement adds little.
- **A feature name such as `examined-calls-v1:<digest>`.** It hides a typed field in a string.

**Limit.** A statement binds the set of files and is not a proof. A collector that writes a
false digest passes. A section with some records and with files skipped is not caught here: the
coverage gaps of the collector own that case. Sections `symbols`, `imports` and `bindings` are not
checked: the host already rejects them when emptied. A third-party collector that claims an empty
checked section must now send the field.

**Checked by** `tests/test_collector_claimed_sections.py`: an emptied section is not PASS for
each checked section; a partial or forged statement is not PASS; the collectors state each empty
checked section; the digest ignores the order and keeps path boundaries; a scan without a parsed
file needs no statement; the error names the section. `native/wire/src/reply_tests.rs` checks the
Rust digest against the Python digest. The strict xfail
`test_a_section_that_is_emptied_is_never_a_pass` of PR #928 passes after both PRs merge.
