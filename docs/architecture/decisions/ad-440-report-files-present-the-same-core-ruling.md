# AD-440 Report files present the same core ruling

**Status.** Proposed. Part of #880. This extends AD-422 and AD-432.

**Decision.**
1. Serve `report --output PATH --format html|json`. The default format is HTML.
   Without `--output`, write no file. `--format` needs `--output`.
2. Keep `validate --output` refused. The CLI at `11da611a5` did not have this option.
   Keep `--html` refused: it was not a flag of release 4.0.1.
3. Write exactly the named file. JSON is the core frame, not the shell result envelope or `architecture.json`.
   HTML is one static page. There are no sidecar files, scripts, external resources or graphs.
4. Add the optional boolean `html` to scan protocol 1. It requests presentation, not facts or a verdict.
   `Ruling::frame` stays the only frame maker. `Ruling::with_html` selects presentation only.
   `native/report` renders the assembled frame of this same typed ruling before it serializes the frame.
5. Carry the page in the optional `html` part: protocol `archkeel-core-html-1`, status and document.
   The strict shell decoder checks the fields, protocol, text and matching status.
   It requires exactly one exact verdict heading for that status and refuses any other verdict heading.
   A requested page without this part refuses, including an old core frame. No file is written.
   An old frame without this part remains valid when no HTML was requested.
6. The shell writes only after `read_frame` accepts the whole frame and its request binding.
   It removes the transport-only HTML part from stdout. Existing text and JSON stdout stay unchanged.
   A completed write keeps the frame exit: PASS 0, FAIL 1, UNKNOWN 2.
7. UNKNOWN and collection-refused frames write reports with the same UNKNOWN or FAIL verdict and all named causes.
   A refusal without an accepted frame writes nothing and says that no report file was written.
   File errors give typed `io_error`, exit 2. Stdout still shows the frame verdict.
   Exit 2 replaces exit 1 of a FAIL when the requested report file cannot be written.
   A run that cannot deliver the requested file is not a clean FAIL. No file error can become PASS.
8. Escape each dynamic text at the HTML boundary. Keep full names; wrap long text without truncation.
   Show rule counts, rule rows, violation details, evidence locations, gaps, unsupported parts and request identity.
   Render details as definition lists and only cited evidence locations as table rows, not a JSON dump.
   Unknown detail shapes use escaped compact single-line text. One escape function protects all dynamic HTML text.
   Show the core code digest, not the crate version. The scan request carries no package version.
   An unavailable identity remains null, never an invented claim.
9. Resolve the parent directory once, including ancestor links, then open and pin that resolved directory.
   Refuse a link in the final component, directories, special files and missing parents. Never create a parent directory.
   Refuse empty and `.` output paths before a scan. Refuse `--output -`: standard output is not a file target; omit `--output`.
   Write and sync a private temporary file in that parent, then atomically replace the named file.
   Replace an existing regular file, as 4.0.1 did. Clean the temporary file after a failed write.
   Platforms without directory handles refuse file output; stdout remains available.
10. `cli/core_output.py` owns received-page decoding and file IO only. It contains no renderer or decision.
    `engine_frame.html` belongs to the existing report component. No model, evaluator or proof maker changes.
    The reviewed public API adds only `Ruling::with_html`; its API baseline names this method.

**Reason.** A user needs a report file without a second decision path.
The old default wrote `architecture.json` and HTML sidecars. Those facts and topology are not available on this line.
An explicit path avoids silent writes into the scanned project and keeps current stdout behavior.

**Rejected.** Rendering in the shell; scanning twice; HTML from a second status; restoring an empty legacy graph;
automatic sidecars; creating missing parents; following final-component links; accepting an old frame without the requested page.

**Limits.** This is not the legacy interactive report or a complete report-v2 payload.
There is no topology projection, saved-input support, filter, baseline or amendment support.
Directory-handle output currently requires POSIX. Windows file output refuses by name with exit 2.
The shell checks the fixed verdict heading but does not render HTML or re-evaluate a rule.
This change adds no PASS and changes no expected native self-check gap.

**Tests.** `tests/test_cli_report_output.py` checks the release core and default CLI, both formats,
the PASS/FAIL/UNKNOWN/refused matrix for both supported profiles, unchanged stdout and exits, escaping,
unsafe paths, overwrite, failed-write cleanup, missing or forged parts and no-frame refusals.
The report crate tests check all typed statuses, escaped long text and a golden refused page.
The existing shell refusal, clone and native self-row tests remain in the gate.
