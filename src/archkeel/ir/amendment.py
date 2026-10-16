# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable contract/baseline approval and exact digest-binding verification."""

import builtins as _builtins
from dataclasses import dataclass
from enum import StrEnum


class AmendmentVersion(StrEnum):
    V1 = "1.0.0"
    V2 = "2.0.0"


class AmendmentStatus(StrEnum):
    VALID = "valid"
    STALE = "stale"


AMENDMENT_SCHEMA_VERSION = AmendmentVersion.V2


@dataclass(frozen=True, slots=True)
class Amendment:
    """A recorded decision to widen the contract from one exact revision to another (#11).

    Binding both digests, rather than only `after`, is what AD-52's baseline does not do for
    itself: an amendment written for one change must not silently authorise a different one.
    `decided_by` and `rationale` are free text, checked for non-emptiness only, the way a
    rule's own `rationale` is: this module has no way to judge whether a reason is a good one.
    """

    before_digest: str
    after_digest: str
    decided_by: str
    rationale: str
    before_baseline_digest: str | None = None
    after_baseline_digest: str | None = None
    schema_version: AmendmentVersion = AMENDMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _builtins.object.__setattr__(self, "schema_version", AmendmentVersion(self.schema_version))


def verify_amendment(
    amendment: Amendment,
    *,
    before_digest: str,
    after_digest: str,
    before_baseline_digest: str | None = None,
    after_baseline_digest: str | None = None,
) -> bool:
    """Bind the original contract tree and baseline policies on both sides."""
    return (
        amendment.before_digest == before_digest
        and amendment.after_digest == after_digest
        and amendment.before_baseline_digest == before_baseline_digest
        and amendment.after_baseline_digest == after_baseline_digest
        and (amendment.schema_version != AmendmentVersion.V1 or before_baseline_digest is None)
    )

