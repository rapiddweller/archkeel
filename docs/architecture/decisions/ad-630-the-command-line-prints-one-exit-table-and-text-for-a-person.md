# AD-630 The command line prints one exit table and text for a person

**Status.** Proposed. Part of #880. Closes the user-experience findings #1317, #1318, #1319, #1320,
#1323 and #1328. It changes defaults of the text and of `report --output`; no exit code changes.

**Reason.** The first user test of 5.0 found a header that said `FAIL` with exit 2, 4,299 lines of
text with the verdict far down, internal codes and numbers in every message, one help text for each
command and a full JSON frame printed after `report --output`.

**Decision.**
1. One exit table (`core_exit.EXIT_TABLE`): 0 PASS, 1 FAIL, 2 UNKNOWN. The help prints it and the
   header states it. The header is `<command>: <WORD> -> exit <code> (<reason>)`, and the word is the
   one that the table gives for the code. When a baseline or a failed file write decides the code,
   the reason says what the frame said and why the code differs. A scan that did not run exits 2;
   with `--baseline` it exits 1, because exit 2 then means that every UNKNOWN is accepted (AD-546);
   the help states both.
2. The text is written in reading order: header, problems of the input, the next action, the
   violations, the rules that wait and the gaps grouped by cause (count and three examples, "and N
   more", `--all` lists all). The text of a project with 78 gaps fits two screens.
3. The text uses a user vocabulary (`core_words`): no machine code, issue number, decision number,
   internal prefix or core path. The path of the root is shown as typed. The JSON keeps the codes.
   `--verbose` adds the core binary, engine and digest.
4. `report --output` prints one line (header and file name); `--json` prints the object and `--text`
   prints the text and a line for the file. Without a terminal the default stays JSON, and the help
   says so.
5. Each command has its own help (`core_help`): options, the output rule, the exit table, two
   examples. `--only` and `--input` are not documented and refuse in plain words; `--topology` says
   that it changes the printed result, not the HTML page.

6. Errors of the input come first and name what to do (#1324). A refused contract is printed as
   `Problem: <file>: <what the core read>` and `Fix: <what to write>`: the syntax place of invalid
   JSON, an example for a `requires` entry, the schema file for the other forms. A configuration
   file that cannot be read is split into missing (with `archkeel init`), a folder, and unreadable.
   The advice is display only (`core_words.contract_fix`); the core still decides every verdict.
