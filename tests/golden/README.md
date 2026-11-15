# Golden replies

Frozen replies of the source collectors ([AD-343](../../docs/architecture/decisions/ad-343-a-collector-reply-is-frozen-as-golden-data-before-its-code-is-deleted.md)).
Each language has `cases.json` and one file for each case. TypeScript also has `RECORDINGS.md`.

Record a case again only with a reason:

```bash
make golden-record LANGUAGE=typescript CASE=h-typescript REASON="why the reply changes"
```

Use `CASE=all` for every case. Set `ARCHKEEL_GOLDEN_PRODUCER=native` to run the golden test
with the native binary.

## Python

The Python directory holds `cases.json` and 14 recorded replies (`*.json.gz`). The sources of the cases are
in `fixtures/golden-python`. A Python case sets `phase`: `full` is the host sequence (providers, then
collection), `providers` is the survey with the provider sources and `imports` is the survey of phase
`imports`. It can also set `features` (`false` requests no gated feature) and `exclude_tests`.

No test compares these replies on `main`: `tests/test_collector_golden_replies.py` runs TypeScript only,
and `make golden-record` builds the TypeScript collector only. There is no `interpreter.json` and no
`RECORDINGS.md` for Python. The files are the record of the Python collector before it was deleted.
