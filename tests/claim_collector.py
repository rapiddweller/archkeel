# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A collector process that sends the Python TypeScript reply with one change (AD-344).

Usage: `claim_collector.py MODE [SECTION]`. The modes:

- `plain`: no change.
- `empty`: remove the records of `SECTION` and its statement of examined files. The claim stays.
- `partial`: remove the records and state all files but one.
- `forged`: remove the records and state a file that is not in the scan.
"""

from __future__ import annotations

import dataclasses
import sys

from archkeel.analyzer.typescript.collect import collect
from archkeel.ir.facts import FactSection, SourceSectionName
from archkeel.ir.facts_codec import decode_request, encode_response
from archkeel.ir.protocol import CollectionResponse


def main() -> int:
    mode = sys.argv[1]
    request = decode_request(sys.stdin.buffer.read())
    facts = collect(request)
    if mode != "plain":
        section = SourceSectionName(sys.argv[2])
        sections = tuple(
            FactSection(item.name, ()) if item.name is section else item for item in facts.sections
        )
        examined = {key: value for key, value in facts.capabilities.examined if key is not section}
        paths = sorted(file.rel_path for file in facts.files)
        if mode == "partial":
            examined[section] = tuple(paths[1:])
        elif mode == "forged":
            examined[section] = (*paths, "not/in/the/scan.ts")
        capabilities = dataclasses.replace(
            facts.capabilities, examined=tuple(sorted(examined.items(), key=lambda i: i[0].value))
        )
        facts = dataclasses.replace(facts, sections=sections, capabilities=capabilities)
    sys.stdout.buffer.write(encode_response(CollectionResponse(facts, request.protocol_version)))
    return 0


raise SystemExit(main())
