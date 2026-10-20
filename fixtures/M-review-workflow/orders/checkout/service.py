from orders.checkout.receipts import Receipt
from orders.checkout.rounding import round_cents
from orders.pricing import price
from orders.storage import save


def place(sku: str, quantity: int, region: str, coupon: str | None = None) -> Receipt:
    receipt = Receipt(sku, quantity, round_cents(price(sku, quantity, region, coupon)))
    save(receipt.sku, receipt.quantity, receipt.total_cents)
    return receipt
