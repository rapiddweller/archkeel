// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Frame metadata and source locations. Only the report ruling writes a verdict.

use std::collections::BTreeMap;

use archkeel_contract::RuleKind;
use archkeel_facts::identity::{evidence_id, sha256_hex};
use archkeel_model::{Input, Reason, Settings};
use archkeel_report::Named;
use archkeel_store::Ingested;
use serde::Serialize;

use crate::section_rows::SectionRow;

/// The code digest of this build: the digest of each native collector of the same source. It is
/// public text, so it detects a stale build and proves no producer (AD-390).
pub(crate) const CODE_DIGEST: &str = env!("ARCHKEEL_CODE_DIGEST");
/// The engine of a frame: the core and its code digest. A build with the test feature `harness`
/// says so after the digest (#1095); the digest itself is the same.
#[cfg(not(feature = "harness"))]
pub(super) const ENGINE: &str = concat!("archkeel-core ", env!("ARCHKEEL_CODE_DIGEST"));
#[cfg(feature = "harness")]
pub(super) const ENGINE: &str = concat!("archkeel-core ", env!("ARCHKEEL_CODE_DIGEST"), "+harness");

#[derive(Serialize, schemars::JsonSchema)]
pub(crate) struct Parts {
    pub(super) measures: Option<archkeel_model::Measures>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) topology: Option<crate::topology_projection::Topology>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) explain: Option<archkeel_report::Explain>,
    pub(super) engine: &'static str,
    pub(super) sections: BTreeMap<&'static str, Vec<SectionRow>>,
    pub(super) unsupported: UnsupportedParts,
    pub(super) self_test: SelfTest,
    pub(super) locations: BTreeMap<String, Location>,
    pub(super) collection_gaps: Vec<CollectionGap>,
    pub(super) contract_digest: Option<String>,
    /// The gaps of the rules without a decision, each with its kind (AD-546).
    pub(super) gaps: Vec<crate::baseline_frame::GapRow>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) baseline: Option<crate::baseline_frame::Part>,
    /// The parts of a system run (AD-616); `crate::system::join` writes it.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) system: Option<SystemFrame>,
}

/// The rows of each section, as rows of the envelope or an error that names the bad row.
pub(crate) fn typed_rows(
    rows: BTreeMap<&'static str, Vec<serde_json::Value>>,
) -> Result<BTreeMap<&'static str, Vec<SectionRow>>, String> {
    rows.into_iter()
        .map(|(name, found)| {
            found
                .into_iter()
                .map(|row| {
                    serde_json::from_value(row).map_err(|error| format!("section {name}: {error}"))
                })
                .collect::<Result<Vec<_>, _>>()
                .map(|found| (name, found))
        })
        .collect()
}

/// The `collect` part of the self-test of a scan (AD-406): the request that the core derived and
/// the digest of each contract file, or the reason that the collector did not run.
#[derive(Serialize, schemars::JsonSchema)]
#[serde(untagged)]
pub(crate) enum Collect {
    Derived {
        #[schemars(with = "archkeel_facts::request::Request")]
        request: serde_json::Value,
        contract_files: BTreeMap<String, String>,
    },
    Refused {
        refused: String,
    },
}

#[derive(Serialize, schemars::JsonSchema)]
pub(super) struct CollectionGap {
    kind: String,
    subjects: Vec<String>,
    reason: String,
    evidence: Vec<String>,
    /// The collector's free text beside the reason, not part of the gap key (AD-540).
    #[serde(skip_serializing_if = "Option::is_none")]
    detail: Option<String>,
}

/// Copy collector coverage gaps for display, without deciding which rules they affect.
pub(super) fn collection_gaps(reply: Option<&Ingested>) -> Vec<CollectionGap> {
    reply
        .into_iter()
        .flat_map(|reply| &reply.reply().facts.coverage.gaps)
        .map(|gap| CollectionGap {
            kind: gap.kind().as_str().to_owned(),
            subjects: gap.subjects.clone(),
            reason: gap.title.clone(),
            evidence: gap
                .evidence_ids
                .iter()
                .map(|id| id.as_str().to_owned())
                .collect(),
            detail: gap.data.collector_message(),
        })
        .collect()
}

pub(super) fn collection_metadata(
    reply: Option<&Ingested>,
) -> (Vec<CollectionGap>, Option<archkeel_model::Measures>) {
    let measures = reply.and_then(|reply| archkeel_model::measure_facts(&reply.reply().facts));
    (collection_gaps(reply), measures)
}

#[derive(Serialize, schemars::JsonSchema)]
pub(super) struct Location {
    path: String,
    line: i64,
}

#[derive(Serialize, schemars::JsonSchema)]
pub(super) struct UnsupportedParts {
    pub(super) sections: BTreeMap<&'static str, String>,
    pub(super) report: Option<String>,
}

#[derive(Serialize, schemars::JsonSchema)]
pub(super) struct SelfTest {
    pub(super) contract: ContractCheck,
    pub(super) reply: ReplyCheck,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) collect: Option<Collect>,
}

#[derive(Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub(super) enum ContractCheck {
    Rules(#[schemars(with = "BTreeMap<String, String>")] BTreeMap<String, RuleKind>),
    Missing(Vec<String>),
    Refused(String),
    NotRead(String),
}

#[derive(Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub(super) enum ReplyCheck {
    Files(usize),
    Refused(String),
    Absent(String),
}

/// The hygiene of the run (AD-466): the checks of the documents that a scan request read, or the
/// one named row of a request without documents.
pub(super) fn hygiene_of(
    engine: &mut crate::engine::Engine,
    (documents, sdk): (Option<&crate::provenance::Documents>, &[String]),
    namespace: &str,
    path: &str,
) -> crate::hygiene::Found {
    let (usable, models) = engine.inputs();
    match documents {
        Some(documents) => crate::hygiene::check(documents, usable, models, namespace, sdk, path),
        None => crate::hygiene::unread(usable),
    }
}

/// The `GapKind` word of the reason that holds a reply that the core cannot verify (AD-546).
const PRODUCER_NOT_VERIFIED_KIND: &str = "producer_not_verified";

/// A reason that names the whole contract: the first of the reply that the core cannot verify, the
/// base reply and the hygiene refusal, when the request has no such reason yet (AD-546 gives each
/// its `GapKind` word, so the shell reads no text).
pub(super) fn hold_contract(
    named: &mut archkeel_report::Named,
    trust: Option<String>,
    base: Option<String>,
    hygiene: Option<(&'static str, String)>,
) {
    if named.contract.is_some() {
        return;
    }
    let held = trust
        .map(|gap| (PRODUCER_NOT_VERIFIED_KIND, gap))
        .or(base.map(|base| ("base", base)))
        .or(hygiene);
    if let Some((kind, text)) = held {
        named.contract = Some(text);
        named.contract_kind = Some(kind);
    }
}

/// The parts of a run that no baseline can accept: a refused or absent reply, a contract that
/// the core could not read, a section or the report that no slice ports (AD-546).
pub(super) fn refusals(
    reply: &ReplyCheck,
    contract: &crate::contract::ContractState,
    sections: &BTreeMap<&'static str, String>,
    report: Option<&String>,
) -> Vec<String> {
    let mut found = Vec::new();
    match reply {
        ReplyCheck::Files(_) => {}
        ReplyCheck::Refused(why) | ReplyCheck::Absent(why) => found.push(format!("reply: {why}")),
    }
    match contract {
        crate::contract::ContractState::Parsed(_) => {}
        crate::contract::ContractState::Missing(paths) => {
            found.push(format!("inside contracts: {}", paths.join(", ")));
        }
        crate::contract::ContractState::Refused(why) => found.push(format!("contract: {why}")),
    }
    found.extend(
        sections
            .iter()
            .map(|(name, why)| format!("section {name}: {why}")),
    );
    found.extend(report.map(|why| format!("report: {why}")));
    found
}

/// Frame bytes and whether the frame names an unsupported or refused part.
pub(crate) struct Answered {
    pub(crate) frame: Vec<u8>,
    pub(crate) names_a_gap: bool,
}

/// Copy validated evidence, including the root contract citation that the settings made.
pub(super) fn locations(
    reply: Option<&Ingested>,
    path: &str,
    bytes: &[u8],
    settings: &Settings,
) -> BTreeMap<String, Location> {
    let mut found: BTreeMap<String, Location> = reply
        .into_iter()
        .flat_map(|reply| &reply.reply().facts.evidence)
        .map(|evidence| {
            (
                evidence.id.as_str().to_owned(),
                Location {
                    path: evidence.file.clone(),
                    line: evidence.line.max(0),
                },
            )
        })
        .collect();
    if let Some(cite) = settings.contract_evidence(&sha256_hex(bytes)) {
        if let Some(line) = [0, 1]
            .into_iter()
            .find(|line| evidence_id(path, *line, *line, 0) == cite)
        {
            found.insert(
                cite.to_owned(),
                Location {
                    path: path.to_owned(),
                    line,
                },
            );
        }
    }
    found
}

/// A refused collection has no contract input. Never parse empty bytes as a contract.
pub(crate) fn refused_scan(reason: &str, html: bool) -> Result<Answered, String> {
    let missing = Reason::MissingInput(Input::Reply);
    let ruling = archkeel_report::rule(
        Err(&missing),
        Named {
            contract: Some(reason.to_owned()),
            contract_kind: Some("other"),
            ..Named::default()
        },
    )
    .map_err(|error| error.to_string())?;
    let parts = Parts {
        measures: None,
        topology: None,
        explain: None,
        engine: ENGINE,
        sections: BTreeMap::new(),
        locations: BTreeMap::new(),
        collection_gaps: Vec::new(),
        contract_digest: None,
        gaps: crate::baseline_frame::gap_rows(&ruling),
        baseline: None,
        system: None,
        unsupported: UnsupportedParts {
            sections: BTreeMap::new(),
            report: None,
        },
        self_test: SelfTest {
            contract: ContractCheck::NotRead(reason.to_owned()),
            reply: ReplyCheck::Absent(reason.to_owned()),
            collect: Some(Collect::Refused {
                refused: reason.to_owned(),
            }),
        },
    };
    let frame = ruling
        .with_html(html)
        .frame(&parts)
        .map_err(|error| error.to_string())?
        .into_bytes();
    Ok(Answered {
        frame,
        names_a_gap: true,
    })
}

#[cfg(test)]
mod tests {
    use super::{evidence_id, locations};

    #[test]
    fn a_contract_location_has_the_citation_and_line_of_its_settings() {
        for (bytes, line) in [(b"{}\n".as_slice(), 1), (b"\n{}\n".as_slice(), 0)] {
            let settings = archkeel_model::Settings::new(String::new(), String::new(), Vec::new())
                .with_contract_source("contract.json", bytes);
            let found = locations(None, "contract.json", bytes, &settings);
            let cite = evidence_id("contract.json", line, line, 0);
            assert_eq!(found[&cite].path, "contract.json");
            assert_eq!(found[&cite].line, line);
            assert!(locations(None, "elsewhere.json", bytes, &settings).is_empty());
            assert!(locations(None, "contract.json", b"[]", &settings).is_empty());
        }
    }
}

/// The part `system` of a frame (AD-616): `crate::system::join` writes it.
#[derive(Serialize, schemars::JsonSchema)]
pub(crate) struct SystemFrame {
    /// The title of the system.
    pub(crate) title: String,
    /// The repository path of the system document.
    pub(crate) document: String,
    /// Each part, in the order of the document.
    pub(crate) parts: Vec<PartRow>,
    /// What crosses between the parts, in the order of the document.
    pub(crate) interfaces: Vec<InterfaceRow>,
}

/// One interface between two parts of a system frame: a crossing that is no import.
#[derive(Serialize, schemars::JsonSchema)]
pub(crate) struct InterfaceRow {
    pub(crate) id: String,
    /// The id of the part that uses the interface.
    pub(crate) source: String,
    /// The id of the part that provides it.
    pub(crate) target: String,
    /// What crosses, in one line.
    pub(crate) title: String,
    /// The repository path of the schema of what crosses.
    pub(crate) schema: String,
}

/// One part of a system frame.
#[derive(Serialize, schemars::JsonSchema)]
pub(crate) struct PartRow {
    pub(crate) id: String,
    pub(crate) title: String,
    /// The repository path of the configuration of the part.
    pub(crate) config: String,
    /// The profile of the collector that read the part, from its collection request.
    pub(crate) profile: Option<String>,
    pub(crate) status: archkeel_report::Status,
    /// The ids of the rules of the part.
    pub(crate) rules: Vec<String>,
}
