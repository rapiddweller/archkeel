# AD-344 Only a producer that the host trusts can give PASS

**Decision.** The host knows who made the facts from how it started the collector. It does not
read this from the reply. Owner decision 1 of issue #880 (2026-11-09): PASS comes only from a
bundled or pinned producer. An external collector gives at most UNKNOWN.

1. `ProducerKind` in `check/ports.py` has three values: `python`, `pinned` and `external`.
2. `observer_for` sets the kind. No `collector_argv` gives `python`: the collector of this
   package, with the adapter version of AD-319 pinned. A `collector_argv` gives `external`.
   A `collector_argv` with `pinned_digest` gives `pinned`.
3. A `pinned` collector is checked before each start. `ProcessCollector.pinned_digest` is
   `sha256:` and 64 lowercase hexadecimal digits. The host hashes the file of `argv[0]` and
   compares it. A different digest is an `execution_error` that names both digests, so the
   scan is UNKNOWN. A pin of another shape is a `ValueError` when the collector is made.
4. An `external` scan adds one `incomplete_scan` diagnostic: subject `scan.collector_argv`,
   "The scan used a configured collector (producer: external). An external collector cannot
   prove a rule." The remedy is "Use the bundled collector, or pin the external collector by
   digest." The existing UNKNOWN rule gives the verdict and the exit code 2.
5. The cap stops PASS. A violation that an external collector reports stays FAIL: a failure is
   safe, and a hidden violation is not. The facts and the report data stay, so a user sees them.
6. The producer kind is in the diagnostic text. No field is new. The command result keeps its
   published schema 12.0 (AD-138): a new diagnostic kind would need schema 13.0.
7. `Observer.producer` defaults to `python`. A collector object that code gives to `Observer`
   is the host's own collector. Only `observer_for` builds an `external` or `pinned` observer.
8. The bundled native binary has no launcher in the host yet (PR 4.3a-5). That launcher gives
   it the kind `python` or a new `bundled` kind, and turns on the version pin and the digest
   check of the shipped binary. This record does not decide that.

**Reason.** Before this change, `[scan].collector_argv` could give PASS with any program that
printed valid facts. The host checked the shape of the reply and not its maker. A native PASS
must come from code that the project builds. The launcher knows this and the wire cannot prove
it: a collector can write any digest in its reply.

**Evidence for no config field now.** The pin covers the file of `argv[0]`. A real external
collector is `node packages/adapter/bin/cli.js` (`tests/test_schema_drift.py`): the pin would
cover `node` and not the script. An honest `[scan].collector_digest` needs a rule for the
arguments, or a self-contained binary. No customer asks for it. A config field also changes the
published `archkeel.schema.json`. The mechanism is tested through `observer_for`, so a config
field later only passes its value.

**Source checkout.** The native tests and the corpus harness start a binary from the checkout
or a Python oracle. They call `observer_for(..., pinned_digest=pin_of(argv[0]))`
(`tests/collector_pin.py`). No config key, flag or environment variable sets a pin. The CLI
passes none, so a customer config stays `external`. Not a test, but a user can also call
`observer_for` in code: that is a deliberate pin of a named file, not a silent PASS.

**Rejected.**
- A trust flag or an environment variable. A repository or a CI file can set it silently.
- A digest from the reply (`adapter.code_digest`). The producer writes it.
- Dropping the observation of an external collector. The native tests need its facts.
- A new diagnostic kind `external_collector`. It needs the schema 13.0 for a text change.

**Limit.**
- The file is read once, before the start. A change between the read and the start is not seen.
- A pin of an interpreter does not cover its script.
- `python` is not an identity: it says only that the host started its own package.

**Check.** `tests/test_collector_producer_trust.py` runs the CLI with `collector_argv` (UNKNOWN,
exit 2, the text), a pinned run (PASS), a changed file (refused) and a malformed pin.
`tests/test_collector_native_verdicts.py` and `tests/test_configured_collector_check.py` pin
the collectors that they start, so their verdicts keep their meaning.
