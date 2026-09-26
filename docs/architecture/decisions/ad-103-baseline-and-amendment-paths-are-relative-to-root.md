# AD-103 Baseline and amendment paths are relative to --root

`validate` resolves a relative `--baseline` or `--amendment`, and so the file `--write-baseline`
or `--write-amendment` writes, against `--root`, the way it already resolves the contract. An
absolute path is used as it is. Either way the resolved path, symlinks included, must lie inside
the root, or the run is `baseline.invalid` or `amendment.invalid`, exit 2; that check is what
keeps a write inside the root. With `--root .`, every path inside the root names the same file
as before; only a path outside it, which `main` accepted, is refused now (#149).

## Why

Measured with the shop sample at a repository root and the Dart sample in `mobile/`, each with
one violation and a baseline of its own, every command run from the repository root:

| `validate` with | `main` | This change |
|---|---|---|
| `--root mobile --baseline architecture-baseline.json` | exit 1, 1 new, 1 resolved, no diagnostic | exit 0 |
| `--root mobile --baseline mobile/architecture-baseline.json` | exit 0 | exit 2, names both paths |
| the same with `--write-baseline` | exit 0 | exit 2, writes nothing |
| `--root mobile --baseline $PWD/mobile/architecture-baseline.json` | exit 0 | exit 0 |
| `--root . --baseline $PWD/architecture-baseline.json` | exit 0 | exit 0 |
| `--root mobile --baseline $PWD/architecture-baseline.json` | exit 1, 1 new, 1 resolved | exit 2, outside the root |
| `--root . --baseline architecture-baseline.json` | exit 0 | exit 0 |

On `main` the first run read the app's contract and the backend's baseline: one command, two
input files, two rules. Its result looked like a regression, not like a wrong file.

## The old spelling fails loudly

`check.validation._root_path` refuses a relative path that, read from a working directory
outside the root, leads into it, while nothing exists at the root-relative path. A working
directory inside the root never triggers it, and an existing root-relative file is always read.
Nothing falls back to the working directory; the refusal is `baseline.invalid`:

```
The validation baseline cannot be read: mobile/architecture-baseline.json is relative to --root
<repo>/mobile: it names <repo>/mobile/mobile/architecture-baseline.json, which does not exist,
not <repo>/mobile/architecture-baseline.json; pass architecture-baseline.json
```

This supersedes AD-61's clause that `--against` simply does not compare a baseline outside the
repository root: such a baseline is refused before any comparison.

## Rejected

- **Keep working-directory paths and reject a baseline whose subjects lie outside
  `[scan].namespace`.** Both samples above use the namespace `shop`, so it would pass the wrong
  file; a component-label subject names no module; a budgets-only baseline has no subject.
- **Fall back to the working directory when the root-relative file is missing.** Two rules
  again, and the fallback is the silent read #149 reports.
- **`--config`'s path syntax** (relative only, no `:`, glob character or backslash). `main`
  accepted an absolute baseline inside the root and a name such as `base[1].json`; containment
  alone keeps a write inside the root.

## Limits

- A path outside the root, which `main` read or wrote, is exit 2.
- A first write into a folder inside the root that repeats the root's name, from outside the
  root (`--root mobile --baseline mobile/x.json --write-baseline` meaning `mobile/mobile/x.json`),
  is refused. Run it from inside the root instead; once the file exists it is read from anywhere.
- `report --output` and `check --output` stay relative to the working directory: they name where
  the caller wants an artifact, not an input. `check --baseline` is a commit SHA.
- The CLI's two removed `args.*.resolve()` calls lower Archkeel's `calls_unresolved`, 502 to 500.

## Tests

`tests/test_cli.py` runs #149's repository from its root with relative and absolute paths, a
nested `mobile/mobile/` file and a first write from `mobile/lib`, and refuses an absolute path,
`..` and a symlink out of the root, read and write, for both options. Demo row
`validation-baseline-root-relative` cites it.
