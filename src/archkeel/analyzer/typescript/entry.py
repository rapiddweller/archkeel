# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Strict stdin/stdout entry point for the TypeScript source collector."""

import json
import sys
from pathlib import Path

from archkeel.analyzer.bootstrap import is_direct_entrypoint
from archkeel.ir.facts_codec import decode_request, encode_response
from archkeel.ir.protocol import CollectionResponse, TypeScriptSettings

from .collect import collect


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--stream-snapshot":
        from .stream import build_snapshot

        request = decode_request(sys.stdin.buffer.read())
        if not isinstance(request.resolver, TypeScriptSettings):
            raise ValueError("TypeScript collector requires the TypeScript resolver")
        summary = build_snapshot(request, Path(sys.argv[2]))
        sys.stdout.write(json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + "\n")
        return 0
    request = decode_request(sys.stdin.buffer.read())
    if not isinstance(request.resolver, TypeScriptSettings):
        raise ValueError("TypeScript collector requires the TypeScript resolver")
    sys.stdout.buffer.write(
        encode_response(CollectionResponse(collect(request), request.protocol_version))
    )
    return 0


if is_direct_entrypoint(__name__):
    raise SystemExit(main())
