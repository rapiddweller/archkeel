class Rule:
    region = "fr"

    def gross(self, net: float) -> float:
        return net * 1.22
