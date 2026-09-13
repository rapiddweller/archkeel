from sample.helpers import first, second


def run(key: str) -> int:
    handlers = {"first": first, "second": second}
    return handlers[key]()
