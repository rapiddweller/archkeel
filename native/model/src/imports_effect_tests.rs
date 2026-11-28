// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: an unresolved import that a gap with an effect names (AD-564). The gap names it only
// when its effect leaves the code of the source unknown: else the import keeps the whole scope
// unknown, because a re-export through it can be a route that no effect covers.

use archkeel_facts::data::{GapData, GapEffect};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName};
use archkeel_facts::vocab::ResolutionDimension;
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

/// A collection gap of the imports at `module` that cites `evidence` and states no effect.
fn collection_gap(module: &str, evidence: Vec<EvidenceId>) -> Record<GapFact> {
    let mut data = GapData::at("site", module);
    data.resolution_dimension = Some(ResolutionDimension::Imports);
    let fact = GapFact::CollectionGap(data);
    let mut record = Record::unknown(FactId::new("UNKNOWN-C"), "site", None, module, fact);
    record.evidence_ids = evidence;
    record
}

#[test]
fn a_resolution_gap_without_an_effect_leaves_the_code_unknown_and_names_a_cited_import() {
    let (mut reply, _, module, evidence) = unresolved().expect("the golden reply");
    let mut cited = evidence.clone();
    cited.push(EvidenceId::new("EVD-more"));
    // A resolution gap states no effect: the code of every module is unknown, so it names each
    // import that it cites. A collection gap of the same shape names only the same site.
    for (site, unknown) in [
        (gap("other.module", cited.clone(), None), 0),
        (gap(&module, evidence.clone(), None), 0),
        (gap(&module, vec![EvidenceId::new("EVD-other")], None), 1),
        (collection_gap("other.module", cited), 1),
        (collection_gap(&module, evidence), 0),
    ] {
        reply.facts.coverage.gaps = vec![site.clone()];
        assert_eq!(
            split(&reply.facts, reply.facts.profile.target_marks(), |_| false).unknown,
            unknown,
            "{:?}",
            site.data
        );
    }
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
        (gap("other.module", cited, None), 0),
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
            split(&reply.facts, reply.facts.profile.target_marks(), |_| false).unknown,
            unknown,
            "{:?}",
            site.data
        );
    }
}
