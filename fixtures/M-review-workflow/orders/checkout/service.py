from orders.checkout.receipts import Receipt
from orders.checkout.rounding import round_cents
from orders.pricing import price
from orders.storage import save


def place(sku: str, quantity: int, region: str) -> Receipt:
    receipt = Receipt(sku, quantity, round_cents(price(sku, quantity, region)))
    save(receipt.sku, receipt.total_cents)
    return receipt
