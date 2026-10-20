class Rule:
    region = "pl"

    def gross(self, net: float) -> float:
        return net * 1.25
