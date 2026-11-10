# Golden replies

Frozen replies of the source collectors ([AD-343](../../docs/architecture/decisions/ad-343-a-collector-reply-is-frozen-as-golden-data-before-its-code-is-deleted.md)).
Each language has `cases.json`, one file for each case and `RECORDINGS.md`.

Record a case again only with a reason:

```bash
make golden-record LANGUAGE=typescript CASE=h-typescript REASON="why the reply changes"
```

Use `CASE=all` for every case. Set `ARCHKEEL_GOLDEN_PRODUCER=native` to run the golden test
with the native binary.

## Python

The sources of the Python cases are in `fixtures/golden-python`. A Python case sets `phase`: `full` is the host sequence (providers, then collection), `providers` is the
survey with the provider sources and `imports` is the survey of phase `imports`. It can also set `features` (`false` requests no gated feature) and
`exclude_tests`.

The reply depends on the interpreter: the text of the standard library, the version and the
built-in modules. `python/interpreter.json` names the interpreter of the recording and the parts
that depend on it. On that interpreter the whole reply must be equal. On another interpreter the
test compares the rest and warns with the parts that it did not compare. The deletion gate
(`ARCHKEEL_GOLDEN_GATE=delete`) fails on another interpreter. Record all cases (`CASE=all`) with
one interpreter: `uv run --python 3.11.12`.
