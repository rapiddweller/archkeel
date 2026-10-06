# AD-103 Baseline and amendment paths are relative to --root

Resolve relative baseline/amendment paths and writes against `--root`. Absolute
paths remain supported. Resolved paths, including symlinks, must stay inside root;
otherwise report `baseline.invalid` or `amendment.invalid`, exit 2 (#149).
Root-dot paths inside it retain their previous meaning.

## Why

A mobile validation run had combined the mobile contract with a backend baseline,
looking like new/resolved debt rather than a wrong file:

| `validate` with | old behavior | root-relative behavior |
|---|---|---|
| `--root mobile --baseline architecture-baseline.json` | exit 1, wrong baseline | exit 0 |
| `--root mobile --baseline mobile/architecture-baseline.json` | exit 0 | exit 2 |
| same with `--write-baseline` | exit 0 | exit 2, no write |
| absolute mobile baseline under mobile root | exit 0 | exit 0 |
| root baseline under root-dot | exit 0 | exit 0 |
| backend absolute baseline under mobile root | wrong-baseline drift | exit 2, outside root |

## The old spelling fails loudly

When cwd is outside root, `_root_path` rejects a relative spelling that resolves
inside root from cwd while its root-relative path is missing. Existing
root-relative files always win; cwd inside root never triggers the guard.
There is no cwd fallback:

```
The validation baseline cannot be read: mobile/architecture-baseline.json is relative to --root
<repo>/mobile: it names <repo>/mobile/mobile/architecture-baseline.json, which does not exist,
not <repo>/mobile/architecture-baseline.json; pass architecture-baseline.json
```

This supersedes AD-61's unchecked outside-root baseline exception.

## Rejected

Namespace validation cannot distinguish scopes sharing a namespace, or budgets-only
baselines. Cwd fallback restores the silent wrong read. Config's stricter filename
syntax would reject previously valid absolute paths or `base[1].json`; containment
already protects writes.

## Limits

Outside-root reads/writes now exit 2. From outside root, first writing
`mobile/mobile/x.json` through repeated-root spelling is refused; run inside root
or use an existing root-relative file. Report/check output paths remain cwd-relative;
`check --baseline` is a commit SHA. Removed CLI resolve calls moved the self
unresolved-call count from 502 to 500.

## Tests

CLI tests cover relative/absolute paths, repeated-root files, first writes,
non-root cwd and path/parent/symlink escapes for both options.
`validation-baseline-root-relative` cites the behavior.
