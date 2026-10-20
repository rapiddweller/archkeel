class Rule:
    region = "de"

    def gross(self, net: float) -> float:
        return net * 1.20
