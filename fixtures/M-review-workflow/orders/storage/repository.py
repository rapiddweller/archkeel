import os

from orders.storage.backends import load_backend


def save(sku: str, quantity: int, total_cents: int) -> None:
    load_backend(os.environ.get("ORDERS_BACKEND", "memory")).write(sku, quantity, total_cents)
