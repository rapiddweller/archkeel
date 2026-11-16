// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: an unresolved import that a gap with an effect names (AD-564). The gap names it only
// when its effect leaves the code of the source unknown: else the import keeps the whole scope
// unknown, because a re-export through it can be a route that no effect covers.

use archkeel_facts::data::GapEffect;
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName};
use archkeel_facts::{GapFact, Record};

use super::split;
use crate::edges::tests::unresolved;

/// A gap of the imports at `module` that cites `evidence`, with `effect`.
fn gap(module: &str, evidence: Vec<EvidenceId>, effect: Option<GapEffect>) -> Record<GapFact> {
    let mut fact = GapFact::resolution("site", module);
    if let GapFact::SourceResolutionGap(data) = &mut fact {
        data.effect = effect;
    }
    let mut record = Record::unknown(FactId::new("UNKNOWN-E"), "site", None, module, fact);
    record.evidence_ids = evidence;
    record
}

#[test]
fn a_gap_with_an_effect_names_an_unresolved_import_only_when_the_effect_covers_its_code() {
    let (mut reply, _, module, evidence) = unresolved().expect("the golden reply");
    let modules = |name: &str| GapEffect::Modules {
        modules: vec![ModuleName::new(name)],
    };
    let edges = GapEffect::Edges {
        sources: vec![ModuleName::new(&module)],
    };
    let layout = GapEffect::Layout {
        modules: vec![ModuleName::new(&module)],
    };
    // A gap elsewhere that cites the import among other uses: its module is not the source.
    let mut cited = evidence.clone();
    cited.push(EvidenceId::new("EVD-more"));
    for (site, unknown) in [
        (gap(&module, evidence.clone(), Some(modules(&module))), 0),
        (
            gap("other.module", cited.clone(), Some(GapEffect::EveryModule)),
            0,
        ),
        (
            gap("other.module", cited.clone(), Some(modules(&module))),
            0,
        ),
        (gap(&module, evidence.clone(), Some(edges)), 1),
        (gap(&module, evidence.clone(), Some(layout)), 1),
        (
            gap(&module, evidence.clone(), Some(modules("other.module"))),
            1,
        ),
        (gap("other.module", cited, None), 1),
        (
            gap(
                &module,
                vec![EvidenceId::new("EVD-other")],
                Some(GapEffect::EveryModule),
            ),
            1,
        ),
    ] {
        reply.facts.coverage.gaps = vec![site.clone()];
        assert_eq!(
            split(&reply.facts, |_| false).unknown,
            unknown,
            "{:?}",
            site.data
        );
    }
}
