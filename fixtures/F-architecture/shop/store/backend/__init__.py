# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Re-export the storage backend the repository writes through."""

from __future__ import annotations

from shop.store.backend.files import read_payload, write_payload

__all__ = ["read_payload", "write_payload"]
