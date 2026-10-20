import importlib
from collections.abc import Callable
from types import ModuleType
from typing import Protocol


class Backend(Protocol):
    def write(self, sku: str, total_cents: int) -> None: ...


# Deployment configuration names the backend; each is imported only when selected.
_LOADERS: dict[str, Callable[[], ModuleType]] = {
    "memory": lambda: importlib.import_module("orders.storage.backends.memory"),
    "sqlite": lambda: importlib.import_module("orders.storage.backends.sqlite"),
}


def load_backend(name: str) -> Backend:
    backend: Backend = _LOADERS[name]().BACKEND
    return backend
