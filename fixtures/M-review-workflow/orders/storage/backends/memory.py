class _Memory:
    def __init__(self) -> None:
        self.rows: list[tuple[str, int]] = []

    def write(self, sku: str, total_cents: int) -> None:
        self.rows.append((sku, total_cents))


BACKEND = _Memory()
