# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Strict stdin/stdout entry point for the TypeScript source collector."""

import sys

from archkeel.ir.facts_codec import decode_request, encode_response
from archkeel.ir.protocol import CollectionResponse, TypeScriptSettings

from .collect import collect


def main() -> int:
    request = decode_request(sys.stdin.buffer.read())
    if not isinstance(request.resolver, TypeScriptSettings):
        raise ValueError("TypeScript collector requires the TypeScript resolver")
    sys.stdout.buffer.write(encode_response(CollectionResponse(collect(request))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
