# AD-318 The host keeps one copy of each observation in explore

**Decision.** `archkeel explore` must not decode, parse or hold its own output a second time.
Three changes make this true. The output of the command does not change.

1. `assemble_observation` parses the model it built. It no longer writes the model to JSON and
   reads it back. `json_arrays` in `ir/codec_wire.py` turns each tuple of the model into a list in
   place, so the parser sees the same shape as before. The step makes no copy.
2. `run_explore` clears its collected facts when both passes end. The report is encoded and
   rendered without them.
3. `run_explore` returns the observation that it encoded, as a third value. The CLI gives it to
   `render_architecture_pages` as `observation`. Without it, the function decodes the bytes. The
   commands `report` and `view` and Studio pass no observation, so they keep this path. The UML
   target of `render_architecture_pages` in `contracts/render.json` gains this parameter. A v2
   amendment binds the change (`ad-318-render-pages-amendment.json`).

**Reason.** `explore` observes twice, once to find the modules and once to record the layout.
Each pass copied the whole model through JSON, and the facts of the first pass stayed alive.
On a React UI (907 files) the Python host held about 1.45 GiB at its peak. The parser took
1.5 % of the collect time. A native collector cannot reduce this peak, so the host path is fixed
first. The measurement is in issue #880.

**Rejected.**
- A module global that hands the observation to the renderer. It hides the data flow and fails
  when two runs share a process.
- A dict payload in the renderer, string interning, `gc.disable()` and `PYTHONMALLOC=malloc`.
  Each gave no gain, or a worse peak on macOS.
- A bounded or streaming decode. It needs a change of the wire format and waits for protocol 10.

**Limit.** `parse_record` still rejects a tuple, because it guards the collector wire. Only the
model that the host builds itself goes through `json_arrays`. The step does not check that a
value is JSON. A value that JSON cannot hold now fails in the parser, not in the encoder. The
render at the peak still builds a report payload of about 285 MiB on Linux. This decision does
not change that.

**Check.**
- `test_explore_checks_its_observation_once_per_pass`: two parses in the passes, none in the
  render, and no JSON decode of the assembled model.
- `test_an_assembled_model_reads_the_same_without_a_json_round_trip`: a model with a contract
  reads equal with and without the round trip.
- `test_json_arrays_turns_tuples_into_lists_in_place_and_reads_like_the_json_round_trip`.
- `test_explore_frees_the_source_facts_before_it_encodes`.
- `test_pages_of_the_explored_observation_equal_pages_of_its_bytes`: the pages are equal.
- `architecture.json` differs from the old output only in `analyzer.code_digest`. Both HTML pages
  are byte-identical.

## Note, 2026-11-08: four host loops do their work once (#880, PR H step 4)

A profile of `explore` on a React UI (907 files) found four loops that repeat work for each pair
of items. They took about 29 % of the host time on Linux. The output does not change.

1. `transitive_paths` (`ir/graph.py`) walks once for each source and keeps the parent of each
   node, so the path is the one `shortest_path` returns. It searched once for each pair: 64 204 times.
2. `derived_unresolved_imports` (`ir/import_gaps.py`) builds the set of (module, evidence ids) of
   the import gaps once. Each import scanned every gap: 28 million `RecordData.get` calls.
3. `CellFindings` (`ir/report_graph.py`) indexes the findings and assessments of a report by
   subject id once. Each import cell scanned the whole report, in the result build and the render.
4. `LazyParsed` (`ir/source_records.py`) parses a raw item at its first lookup. The dependency
   scope check in `check/observation.py` runs only for an incomplete scan and asks for a few gap
   records. It parsed all of them first.

**Limit.** With lazy parsing an invalid internal record fails later: the model parser in
`assemble_observation` still reads every record. A parse error inside a lookup ends the check
without a proof. `LazyParsed` is a new public name of `ir`; `ad-318-host-loops-amendment.json`
binds it. `archkeel.api` and the file sizes of AD-314 do not grow.
**Rejected.** A faster `_json_value` in `facts_codec.py` (PR 3 and PR 6 replace it), a path cache
across the two passes, and a module cache keyed by `id(report)`. **Not done.** The three
validations of the same facts, the render rebuild and the repeat of pass 2 wait for protocol 10.
**Check.** `test_graph_transitive_paths.py`, `test_source_import_gaps.py`,
`test_report_cell_findings.py` and `test_collector_lazy_certify.py` keep each old definition as an oracle.
