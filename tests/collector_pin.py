# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The pin of a collector that a test starts itself (AD-344).

A customer config has no pin. A test passes this one to `observer_for`, so that a scan with its own
collector keeps its verdict instead of the cap of an external collector.
"""

import hashlib
from pathlib import Path
from typing import Any

from archkeel.check.observe import Observer
from archkeel.check.ports import SourceCollector
from archkeel.ir.state_facts import ProducerKind


def pin_of(program: str) -> str:
    return "sha256:" + hashlib.sha256(Path(program).read_bytes()).hexdigest()


def trusted(collector: SourceCollector, **options: Any) -> Observer:
    """An observer for a collector object of the host, as the tests of Core build it (AD-344)."""
    return Observer(collector, producer=ProducerKind.PYTHON, **options)
