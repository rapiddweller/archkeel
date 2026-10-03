# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Strict stdin/stdout entry point for the Dart source collector."""

import sys

from archkeel.ir.facts_codec import decode_request, encode_response
from archkeel.ir.protocol import CollectionResponse, DartSettings

from .collect import collect


def main() -> int:
    request = decode_request(sys.stdin.buffer.read())
    if not isinstance(request.resolver, DartSettings):
        raise ValueError("Dart collector requires the Dart resolver")
    response = CollectionResponse(collect(request))
    sys.stdout.buffer.write(encode_response(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
