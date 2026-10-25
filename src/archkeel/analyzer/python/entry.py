# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Strict stdin/stdout entry point for the Python source collector."""

import sys
import threading

from archkeel.analyzer.bootstrap import is_direct_entrypoint
from archkeel.ir.facts_codec import decode_request, encode_response
from archkeel.ir.protocol import CollectionResponse, PythonCollectionPhase, PythonSettings

from .collect import collect, provider_sources

# Sympy's resolvent_lookup.py nests 568 levels. The default limit of 1000 frames is too low.
_RECURSION_LIMIT = 20_000
# The walk runs on a worker thread. Its large stack stops a high limit from crashing Windows.
_STACK_BYTES = 64 * 1024 * 1024


def main() -> int:
    request = decode_request(sys.stdin.buffer.read())
    if not isinstance(request.resolver, PythonSettings):
        raise ValueError("Python collector requires the Python resolver")
    facts = collect(request)
    providers = (
        provider_sources(request, facts)
        if request.resolver.phase is PythonCollectionPhase.PROVIDERS
        else ()
    )
    response = CollectionResponse(facts, request.protocol_version, providers)
    sys.stdout.buffer.write(encode_response(response))
    return 0


def _run_with_deep_recursion() -> int:
    # ponytail: ceiling is about 8000 operators in one chain; iterative walkers are the next step.
    # A worker that raises keeps status 1; threading prints its traceback to stderr.
    status = 1

    def run() -> None:
        nonlocal status
        status = main()

    threading.stack_size(_STACK_BYTES)
    sys.setrecursionlimit(_RECURSION_LIMIT)
    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    return status


if is_direct_entrypoint(__name__):
    raise SystemExit(_run_with_deep_recursion())
