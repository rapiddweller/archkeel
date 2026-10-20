class Rule:
    region = "at"

    def gross(self, net: float) -> float:
        return net * 1.19
