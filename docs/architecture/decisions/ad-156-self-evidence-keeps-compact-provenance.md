# AD-156 Self evidence keeps compact provenance

Commit `fixtures/D-self/result.json` and `provenance.json`; generate the full JSON/HTML
locally with `make self-observation` or lazily during tests (#316). The large generated JSON
adds review noise and merge conflicts without being a separate source of truth.

A session fixture shares one validated CLI report across local pytest workers using a
portable dev-only file lock. An atomic result marker publishes only complete output;
failed or interrupted generation cannot become cached evidence. Each session starts fresh.
Schema mutation tests decode their own dictionaries from immutable shared bytes.

Provenance keeps only the checker digest and a canonical observation digest. Only Git
HEAD/dirty are normalized; source, analyzer, contract, Python version, coverage, UNKNOWNs
and every record remain in the comparison. Tests recompute both digests independently.
The saved stdout result is checked separately.

A plain session fixture was rejected: xdist would repeat the scan per worker. Upfront
controller generation was rejected because unrelated tests would scan this repository.
History rewriting and a persistent cache are outside this change.

Checks: `tests/test_self_fixture.py`, `tests/test_self.py`, all self-observation consumers,
including own-UML browser tests, and paired same-source JUnit/wall timings with the
existing Make test options.
