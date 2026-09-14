# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Accepted state is data; only the CI accept path may write it."""

from dataclasses import dataclass

from .measurements import Measurements
from .model import Diagnostic, DiagnosticError

LOCK_PATH = "architecture-accepted.json"


class LockError(DiagnosticError):
    def __init__(self, message: str) -> None:
        super().__init__(
            Diagnostic(
                "parse_error",
                LOCK_PATH,
                f"The accepted reference cannot be verified: {message}",
                "Restore the valid CI lock and its bound inputs; "
                "do not create an empty replacement.",
            )
        )


@dataclass(frozen=True, slots=True)
class AcceptedLock:
    accepted_commit: str
    observation_digest: str
    config_digest: str
    checker_digest: str
    measurements: Measurements
    approval_ref: str


def verify_observation(
    lock: AcceptedLock, *, observation_digest: str, measurements: Measurements
) -> None:
    if observation_digest != lock.observation_digest or measurements != lock.measurements:
        raise LockError("accepted observation differs from the CI lock")
