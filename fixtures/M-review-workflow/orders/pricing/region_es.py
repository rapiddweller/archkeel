class Rule:
    region = "es"

    def gross(self, net: float) -> float:
        return net * 1.21
