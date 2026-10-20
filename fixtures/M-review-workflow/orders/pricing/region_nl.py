class Rule:
    region = "nl"

    def gross(self, net: float) -> float:
        return net * 1.24
