# Golden replies

Frozen replies of the source collectors ([AD-343](../../docs/architecture/decisions/ad-343-a-collector-reply-is-frozen-as-golden-data-before-its-code-is-deleted.md)).
The TypeScript directory has `cases.json`, `RECORDINGS.md`, and one file for each case.

Record a case again only with a reason:

```bash
make golden-record LANGUAGE=typescript CASE=h-typescript REASON="why the reply changes"
```

Use `CASE=all` for every case. Set `ARCHKEEL_GOLDEN_PRODUCER=native` to run the golden test
with the native binary.
