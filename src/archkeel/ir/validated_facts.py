# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Remember which SourceFacts object the decoder validated, so that Core checks it once (AD-338).

`decode_response` is the trust boundary to the collector. Its result is frozen all the way
down, so an object that passed stays valid. Core checks every other object, even one built from
the parts of a decoded object: the proof belongs to the object and never to its parts.
"""

from __future__ import annotations

from weakref import WeakValueDictionary

from .claimed_sections import check_examined
from .facts import SourceFacts
from .facts_validation import validate_source_facts

# The key is the identity of the object. The value is the object itself, held weakly: the entry
# goes when the object goes, so a new object with a reused identity has no proof.
_DECODED: WeakValueDictionary[int, SourceFacts] = WeakValueDictionary()


def _validate(facts: SourceFacts) -> None:
    """Check the facts alone, then the statement that each file was examined (AD-344)."""
    validate_source_facts(facts)
    check_examined(facts)


def validate_decoded_facts(facts: SourceFacts) -> None:
    """Validate the facts that the decoder built and remember this exact object."""
    _validate(facts)
    _DECODED[id(facts)] = facts


def ensure_valid_source_facts(facts: SourceFacts) -> None:
    """Validate the facts, except an object that the decoder already validated."""
    if not is_decoded(facts):
        _validate(facts)


def is_decoded(facts: SourceFacts) -> bool:
    """Tell if this exact object, not an equal or changed copy, passed the decoder check."""
    return _DECODED.get(id(facts)) is facts
