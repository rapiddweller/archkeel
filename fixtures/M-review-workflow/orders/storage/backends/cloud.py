import json
import os

import boto3


class _S3:
    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self.client = boto3.client("s3")

    def write(self, sku: str, quantity: int, total_cents: int) -> None:
        body = json.dumps({"sku": sku, "quantity": quantity, "cents": total_cents})
        self.client.put_object(Bucket=self.bucket, Key=f"receipts/{sku}.json", Body=body)


BACKEND = _S3(os.environ.get("ORDERS_BUCKET", "orders-receipts"))
