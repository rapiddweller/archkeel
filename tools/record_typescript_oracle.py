# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The retired recorder of the last Python TypeScript oracle (AD-394).

The source analyzer is main commit 2a3b6eca0. Python 3.11.12 made the recordings.
The manifest in tests/typescript_oracle records each test call, SHA-256 and byte count.
Each .bin member of a per-kind ZIP is a gzip archive (mtime=0). Its payload is the exact collector
wire reply, or deterministic JSON for a syntax, UMD or internal-record result.
tests/typescript_legacy_parser.json.gz also holds each source probe, its syntax and full facts.

Before deletion, the recorder ran the migrated tests with ARCHKEEL_RECORD_TYPESCRIPT=1.
ARCHKEEL_PRIVATE_UI selected the public Excalidraw corpus. ARCHKEEL_RECORDS_CORPORA selected
x35 (scope ui) and Excalidraw (scope .). The six parity files, script syntax and dependencies,
small scaling cases, locale tests, existing golden tests and retained TypeScript tests ran.
The last Python parser tests also supplied 421 source cases through record_parser_probe.
Every call used the unchanged Python analyzer, not native output. The tests ran again with
recording disabled before deletion. Ten separate golden faults failed a migrated test.

This tool cannot run after deletion. The live producers and capture hooks are gone.
Keep the recordings read-only. New behavior needs a native test with an independent expected
result, not an oracle made from the native collector itself.
"""


def capture(*_args: object) -> None:
    raise RuntimeError("typescript_oracle_retired: the Python analyzer no longer exists")


if __name__ == "__main__":
    raise SystemExit("typescript_oracle_retired: these recordings cannot be regenerated")
