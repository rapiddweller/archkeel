# Pledge
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from sample.helpers import first, second


def run(key: str) -> int:
    handlers = {"first": first, "second": second}
    return handlers[key]()
