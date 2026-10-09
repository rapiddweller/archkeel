# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Serve the source-only Dart collection protocol."""

import sys

from archkeel.ir.facts_codec import decode_request, encode_response
from archkeel.ir.protocol import CollectionResponse, DartSettings

from .collect import collect


def main() -> int:
    request = decode_request(sys.stdin.buffer.read())
    if not isinstance(request.resolver, DartSettings):
        raise ValueError("Dart collector requires the Dart resolver")
    sys.stdout.buffer.write(encode_response(CollectionResponse(collect(request))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
