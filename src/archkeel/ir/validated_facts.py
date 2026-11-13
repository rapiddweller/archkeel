# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Remember which SourceFacts object the decoder validated, so that Core checks it once (AD-338).

`decode_response` is the trust boundary to the collector. Its result is frozen all the way
down, so an object that passed stays valid. Core checks every other object, even one built from
the parts of a decoded object: the proof belongs to the object and never to its parts.
"""

from __future__ import annotations

from dataclasses import replace
from weakref import WeakValueDictionary

from .facts import SourceFacts
from .facts_validation import validate_source_facts
from .state_facts import VerifiedBinary

# The key is the identity of the object. The value is the object itself, held weakly: the entry
# goes when the object goes, so a new object with a reused identity has no proof.
_DECODED: WeakValueDictionary[int, SourceFacts] = WeakValueDictionary()


def validate_decoded_facts(facts: SourceFacts) -> None:
    """Validate the facts that the decoder built and remember this exact object."""
    validate_source_facts(facts)
    _DECODED[id(facts)] = facts


def accept_store_facts(facts: SourceFacts) -> None:
    """Remember facts that the Rust store validated (AD-346): its generic checks ran once."""
    _DECODED[id(facts)] = facts


def ensure_valid_source_facts(facts: SourceFacts) -> None:
    """Validate the facts, except an object that the decoder already validated."""
    if not is_decoded(facts):
        validate_source_facts(facts)


def is_decoded(facts: SourceFacts) -> bool:
    """Tell if this exact object, not an equal or changed copy, passed the decoder check."""
    return _DECODED.get(id(facts)) is facts


def with_verified_binary(facts: SourceFacts, binary: VerifiedBinary) -> SourceFacts:
    """Attach host identity without changing the validated wire facts."""
    ensure_valid_source_facts(facts)
    result = replace(facts, verified_binary=replace(binary, runtime=facts.runtime))
    _DECODED[id(result)] = result
    return result
