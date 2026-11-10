# AD-344 Only a producer that the host trusts can give PASS

**Decision.** The host knows who made the facts from how it started the collector. It does not
read this from the reply. Owner decision 1 of issue #880 (2026-11-09): PASS comes only from a
bundled or pinned producer. An external collector gives at most UNKNOWN.

1. `ProducerKind` in `ir/facts.py` has three values: `python`, `pinned` and `external`.
   `check/ports.py` re-exports it for the CLI.
2. `observer_for` sets the kind. No `collector_argv` gives `python`: the collector of this
   package, with the adapter version of AD-319 pinned. A `collector_argv` gives `external`.
   A `collector_argv` with `pinned_digest` gives `pinned`.
3. A `pinned` collector is checked before each start. `ProcessCollector.pinned_digest` is
   `sha256:` and 64 lowercase hexadecimal digits. The host resolves `argv[0]` once to an
   absolute path, hashes that file and starts exactly that path. A bare name comes from `PATH`
   only, never from the scanned root. A file inside the scanned root is refused. A different
   digest is an `execution_error` that names both digests, so the scan is UNKNOWN. A pin of
   another shape is a `ValueError` when the collector is made.
4. An `external` scan adds one `incomplete_scan` diagnostic: subject `scan.collector_argv`,
   "The scan used a configured collector (producer: external). An external collector cannot
   prove a rule." The remedy is "Use the bundled collector, or pin the external collector by
   digest." The existing UNKNOWN rule gives the verdict and the exit code 2.
5. The cap stops PASS. A violation that an external collector reports stays FAIL.
   The facts and the report data stay.
6. The host records the kind in the observation: the field `producer_kind`. Observation schema
   2.10.0 and command result 13.0.0 add it (AD-138). Schemas 2.9.0 and 12.0 stay as they are.
   From 2.10.0 the field is required. An older `schema_version` with the field is refused. Both
   are parse errors, so the result is UNKNOWN. The diagnostic kind stays `incomplete_scan`:
   a new kind would need a new result schema too.
7. `observation_diagnostics` adds a cap diagnostic when the kind is `external` or absent. For an
   absent kind the claim is "producer not recorded" and the remedy is to run the scan again
   with this version. A live scan and `report --input` use it, so a saved scan cannot become
   PASS. Consequence: a file that an older version wrote has no kind. It shows UNKNOWN, also
   when a bundled collector made it, until the scan is saved again.
8. `Observer.producer` has no default. Only `observer_for` derives it from the launch.
9. The bundled native binary has no launcher in the host yet (PR 4.3a-5). That launcher gives
   it the kind `python` or a new `bundled` kind and turns on the digest check of the binary.

**Reason.** `[scan].collector_argv` could give PASS with any program that printed valid facts.
A native PASS must come from code that the project builds. The launcher knows this and the
wire cannot prove it: a collector can write any digest in its reply.

**No config field now.** The pin covers the file of `argv[0]`. A real collector is
`node packages/adapter/bin/cli.js` (`tests/test_schema_drift.py`): the pin would cover `node`
and not the script. An honest `[scan].collector_digest` needs a rule for the arguments. No
customer asks for it, and it changes the published `archkeel.schema.json`.

**Source checkout.** Native tests and the corpus harness start a binary from the checkout or
a Python oracle. They call `observer_for(..., pinned_digest=pin_of(argv[0]))`
(`tests/collector_pin.py`). No config key, flag or environment variable sets a pin, so a
customer config stays `external`. A pin in code names one file: it is not a silent PASS.

**Rejected.**
- A trust flag or an environment variable, or a digest from the reply: both are set silently.
- Dropping the facts of an external collector. The native tests need them.
- A new diagnostic kind `external_collector`. It needs a new result schema.

**Limit.**
- The file is read once, before the start. A change before the start is not seen.
- A pin of an interpreter does not cover its script. A future `collector_digest` setting must
  pin the whole command, the interpreter and the script, and not `argv[0]` alone.
- `report --input` trusts the saved file. The marker stops a re-run from turning an external
  scan into PASS. It does not stop a hand-made file: artifact integrity is out of scope here.

**Check.** `tests/test_collector_producer_trust.py` runs the CLI with `collector_argv` (UNKNOWN,
exit 2), a pinned run (PASS), a changed file, a violation (FAIL) and `report --input` of a saved
external scan (UNKNOWN). It reads a 2.9.0 file without the field (UNKNOWN, "producer not
recorded"), a 2.10.0 file without it and a 2.9.0 file with it (parse error, UNKNOWN). A pinned
file inside the scanned repository gives UNKNOWN through `run_report`. `pinned_path` has unit
tests for `PATH` and relative entries. Tests that start their own collector pin it. The honest
false-PASS probe stays external.
