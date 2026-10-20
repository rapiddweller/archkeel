import sqlite3


class _Sqlite:
    def write(self, sku: str, total_cents: int) -> None:
        with sqlite3.connect(":memory:") as connection:
            connection.execute("create table if not exists receipts (sku text, cents int)")
            connection.execute("insert into receipts values (?, ?)", (sku, total_cents))


BACKEND = _Sqlite()
