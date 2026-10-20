import json
import os
from pathlib import Path


class _JsonLines:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, sku: str, quantity: int, total_cents: int) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"sku": sku, "quantity": quantity, "cents": total_cents}) + "\n")


BACKEND = _JsonLines(Path(os.environ.get("ORDERS_FILE", "receipts.jsonl")))
