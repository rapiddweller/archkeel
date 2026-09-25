# AD-103 Baseline and amendment paths are relative to --root

`validate` resolves `--baseline` and `--amendment`, and so the files `--write-baseline` and
`--write-amendment` write, relative to `--root`, the way it already resolves the contract and
`--config` (AD-101). The path gets `--config`'s checks: a safe POSIX relative path, no `..`, no
absolute path, and a resolved target, symlinks included, inside the root; anything else is
exit 2. With `--root .`, the common case and Archkeel's own `make self-validate`, nothing
changes (#149).

## Why

Measured with the shop sample at a repository root and the Dart sample in `mobile/`, each with
one violation and a baseline of its own, every command run from the repository root:

| Command | `main` | This change |
|---|---|---|
| `validate --root mobile --baseline architecture-baseline.json` | exit 1, `baseline_new` 1, `baseline_resolved` 1, no diagnostic | exit 0 |
| `validate --root mobile --baseline mobile/architecture-baseline.json` | exit 0 | exit 2, names both paths |
| the same with `--write-baseline` | exit 0 | exit 2, writes nothing |
| `validate --root . --baseline architecture-baseline.json` | exit 0 | exit 0 |

On `main` the first run read the app's contract and the backend's baseline: one command, two
input files, two rules. Its result looked like a regression, one new violation and one
resolved, not like a wrong file.

## The old spelling fails loudly

A caller that still passes the root-prefixed path is told so, and nothing falls back to the
working directory:

```
--baseline mobile/architecture-baseline.json is relative to --root <repo>/mobile: it names
<repo>/mobile/mobile/architecture-baseline.json, which does not exist, not
<repo>/mobile/architecture-baseline.json; pass --baseline architecture-baseline.json
```

`cli.config.root_file` refuses a path that, read from a working directory outside the root,
leads into it, while nothing exists at the root-relative path. A write would otherwise create
`mobile/mobile/`. A working directory inside the root never triggers it, and a file that exists
at the root-relative path is always the one read.

## Rejected

- **Keep working-directory paths and reject a baseline whose subjects lie outside
  `[scan].namespace`.** Both samples above use the namespace `shop`, so it would pass the wrong
  file; a component-label subject names no module; a budgets-only baseline has no subject.
- **Fall back to the working directory when the root-relative file is missing.** Two rules
  again, and the fallback is the silent read #149 reports.
- **Accept an absolute path.** `--config` does not, and one rule covers every input file.

## Limits

- An absolute or escaping `--baseline` or `--amendment` is exit 2 now; a CI job that passed
  `$PWD/known-violations.json` passes the root-relative path instead.
- `report --output` and `check --output` stay relative to the working directory: they name where
  the caller wants an artifact, not an input the scan reads. `check --host-records` is a CI file
  the caller authenticates, outside the scanned tree; `check --baseline` is a commit SHA.
- The two `args.*.resolve()` calls this removes lower Archkeel's own `calls_unresolved` from 502
  to 500, written back to `architecture-baseline.json`.

## Tests

`tests/test_cli.py`: `test_baseline_is_read_relative_to_root_like_the_contract` and
`test_amendment_is_written_and_read_relative_to_root` run #149's repository from its root;
`test_root_relative_inputs_stay_inside_the_root` covers an absolute path, `..` and a symlink out
of the root for both options. Row `validation-baseline-root-relative` of
`docs/architecture-demo.md` cites them.
