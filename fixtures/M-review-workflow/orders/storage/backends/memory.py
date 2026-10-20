class _Memory:
    def __init__(self) -> None:
        self.rows: list[tuple[str, int, int]] = []

    def write(self, sku: str, quantity: int, total_cents: int) -> None:
        self.rows.append((sku, quantity, total_cents))


BACKEND = _Memory()
