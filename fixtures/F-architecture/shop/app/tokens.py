# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Generate repeatable tokens for seeded runs."""

import secrets


def token_for_run(seeded: bool) -> str:
    if seeded:
        return "fixed-token"
    return secrets.token_hex(8)
