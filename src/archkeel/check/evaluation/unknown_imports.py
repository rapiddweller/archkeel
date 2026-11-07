# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Build the UNKNOWN failure that Core derives for an unresolved import."""

from archkeel.ir.facts import SOURCE_RESOLUTION_GAP_KIND
from archkeel.ir.facts_codec import RawRecord, classified
from archkeel.ir.model import EvidenceClass, stable_id


def unknown_import_failure(item: RawRecord, reason: str) -> RawRecord:
    return classified(
        item_id=stable_id("UNKNOWN-IMPORT", item["id"]),
        evidence_class=EvidenceClass.UNKNOWN,
        area="analysis_coverage",
        kind=SOURCE_RESOLUTION_GAP_KIND,
        title=reason,
        subjects=item["subjects"],
        evidence_ids=item["evidence_ids"],
        fact_ids=[item["id"]],
        data={"source_module": item["data"]["source_module"], "reason": reason},
    )
