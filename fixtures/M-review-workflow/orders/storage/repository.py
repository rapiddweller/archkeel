import os

from orders.storage.backends import load_backend


def save(sku: str, total_cents: int) -> None:
    load_backend(os.environ.get("ORDERS_BACKEND", "memory")).write(sku, total_cents)
