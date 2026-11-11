# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Strict stdin/stdout entry point for the Python source collector."""

import sys
import threading

from archkeel.analyzer.bootstrap import is_direct_entrypoint
from archkeel.ir.facts_codec import decode_request, encode_response
from archkeel.ir.protocol import (
    CollectionResponse,
    PythonCollectionPhase,
    PythonProviderSource,
    PythonSettings,
)

from .collect import collect, complete_collection, one_pass_requested, provider_sources
from .source import RECURSION_LIMIT

# Sympy's resolvent_lookup.py nests 568 levels. The default limit of 1000 frames is too low.
# The walk runs on a worker thread. Its large stack stops a high limit from crashing Windows.
_STACK_BYTES = 64 * 1024 * 1024


def main() -> int:
    request = decode_request(sys.stdin.buffer.read())
    if not isinstance(request.resolver, PythonSettings):
        raise ValueError("Python collector requires the Python resolver")
    surveying = request.resolver.phase is PythonCollectionPhase.PROVIDERS
    providers: tuple[PythonProviderSource, ...] = ()
    if surveying and one_pass_requested(sys.argv[1:]):
        # The host asked for the survey and the collection together (AD-358): no second start.
        facts = complete_collection(request)
    else:
        facts = collect(request)
        providers = provider_sources(request, facts) if surveying else ()
    response = CollectionResponse(facts, request.protocol_version, providers)
    sys.stdout.buffer.write(encode_response(response))
    return 0


def _run_with_deep_recursion() -> int:
    # ponytail: a module nested deeper than MAX_AST_DEPTH is skipped with a coverage gap.
    # A worker that raises keeps status 1; threading prints its traceback to stderr.
    status = 1

    def run() -> None:
        nonlocal status
        status = main()

    threading.stack_size(_STACK_BYTES)
    sys.setrecursionlimit(RECURSION_LIMIT)
    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    return status


if is_direct_entrypoint(__name__):
    raise SystemExit(_run_with_deep_recursion())
