# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import importlib
from collections.abc import Callable
from types import ModuleType
from typing import Protocol


class Backend(Protocol):
    def write(self, sku: str, quantity: int, total_cents: int) -> None: ...


# The cloud backend needs the optional `cloud` extra (boto3); deployments without it must
# still start, so each backend is imported only when configuration selects it.
_LOADERS: dict[str, Callable[[], ModuleType]] = {
    "memory": lambda: importlib.import_module("orders.storage.backends.memory"),
    "file": lambda: importlib.import_module("orders.storage.backends.file"),
    "cloud": lambda: importlib.import_module("orders.storage.backends.cloud"),
}


def load_backend(name: str) -> Backend:
    if name not in _LOADERS:
        raise ValueError(f"unknown ORDERS_BACKEND {name!r}; expected one of {sorted(_LOADERS)}")
    backend: Backend = _LOADERS[name]().BACKEND
    return backend
