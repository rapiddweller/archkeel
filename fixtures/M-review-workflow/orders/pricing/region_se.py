class Rule:
    region = "se"

    def gross(self, net: float) -> float:
        return net * 1.26
