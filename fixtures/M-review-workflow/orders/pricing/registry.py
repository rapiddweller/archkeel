from orders.pricing import (
    region_at,
    region_de,
    region_es,
    region_fr,
    region_it,
    region_nl,
    region_pl,
    region_se,
)
from orders.pricing.base import TaxRule

RULES: dict[str, TaxRule] = {
    module.Rule.region: module.Rule()
    for module in (
        region_at,
        region_de,
        region_es,
        region_fr,
        region_it,
        region_nl,
        region_pl,
        region_se,
    )
}
