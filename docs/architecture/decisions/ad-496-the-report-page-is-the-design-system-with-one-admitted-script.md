# AD-496 The report page uses the design system and one script that the policy admits by hash

**Status.** Proposed. Part of #880. It replaces point 3 of AD-440 and the page rules of its point 8.

**Decision.**
1. The page loads the design system of the owner: the two font files (Geist and JetBrains Mono,
   inline as base64), the tokens, `bundle.css` and the local rules `report.css`. The files are in
   `native/report/assets/` and are built into the core. A test compares the theme script with its
   design-system source. The page loads no other resource and makes no request.
2. The page holds exactly one script: `archkeel-theme.js`, the theme switch of the design
   system, byte for byte. The policy is `default-src 'none'; style-src 'unsafe-inline'; font-src data:;
   img-src data:; script-src 'sha256-<hash>'; base-uri 'none'; form-action 'none'`. The constant
   `THEME_HASH` is the SHA-256 of the file; a test computes it again. Without the script the theme follows the
   system, and print is always light. Fold, switch and jump need no other script.
3. A link inside the page (`href="#..."`) is allowed. A link to another document is not.
4. `<h1>Verdict: STATUS</h1>` stays the one exact heading that the shell checks (AD-440 point 5).
5. The order is: verdict and next steps, the architecture picture, the violated places. The parts
   that follow still show the frame as before; a later record replaces them.
6. The picture is a component map when the run has at most 12 components and at most 30 dependencies
   between them, else a matrix. A narrow screen shows the matrix. A run without a topology has no picture.
7. A violated place is one block: one import that breaks several rules is one block that lists
   each rule with its sides (`explain.rules`). A cycle is one block with its closed path
   (`explain.cycles`), each step with file and line. At most 100 places show; a cut states both numbers.
8. `report --output x.html` also asks the core for the topology, which is transport for the page. The
   shell removes it from stdout unless the user passed `--topology`, so the output of the run stays as before.
9. The page copies the frame. It decides no verdict and names no language.

**Reason.** A reader needs the picture and the places of the exceptions before a list of rules. The
design system is one file set for the Report and for Studio. A script that is not hashed cannot run.

**Rejected.** A page without script: the owner asked for the theme switch. A script from a file:
the page must be one file. `unsafe-inline` for scripts: it admits any script. Subset fonts: the
full files fit the budget.

**Limits.** The page is at most 600,000 bytes on the core self run (about 290,000 today). Below a
file, the frame holds no class, function or call, so the page shows no such level. A map of a cycle
between components is a matrix mark, not a ring.

**Tests.** `tests/test_cli_report_page.py` (policy hash, no resource, exact heading, seven cycle blocks,
budget on five runs, stdout unchanged). Block and picture tests in `native/report/src/html_tests.rs`.
