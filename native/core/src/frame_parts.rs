// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Frame metadata and source locations. Only the report ruling writes a verdict.

use std::collections::BTreeMap;
use std::time::Duration;

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
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub(super) explorer: Vec<crate::explorer::ExplorerPart>,
    pub(super) measures: Option<archkeel_model::Measures>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) topology: Option<crate::topology_projection::Topology>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) explain: Option<archkeel_report::Explain>,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    pub(super) rule_rationales: BTreeMap<String, String>,
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
    /// The system of the page of a part (E4): `engine_frame::write` takes it out for the page, so
    /// the frame does not carry it.
    #[serde(skip_serializing_if = "Option::is_none")]
    #[schemars(skip)]
    pub(super) part_of: Option<PartOf>,
}

/// The system of the page of one part (E4, #1451): the titles come from the system document.
#[derive(Serialize)]
pub(crate) struct PartOf {
    pub(crate) system: String,
    pub(crate) part: String,
    pub(crate) href: Option<String>,
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
        #[serde(skip_serializing_if = "Option::is_none")]
        target: Option<String>,
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
    holds_budgets: bool,
) -> crate::hygiene::Found {
    let (usable, models) = engine.inputs();
    match documents {
        Some(documents) => crate::hygiene::check(
            documents,
            usable,
            models,
            namespace,
            sdk,
            path,
            holds_budgets,
        ),
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
    /// The seconds of the phases (#659). `None` when a scan was refused, in whole or in a part of a
    /// system run. Not part of the frame.
    pub(crate) timings: Option<Phases>,
    /// The request asked for the timings: the core then writes one timings line on standard error.
    pub(crate) timings_asked: bool,
}

// The wall-clock seconds of the phases of one scan (#659, AD-878): `prepare` (configuration, Git
// state, survey, inside contracts, provenance documents), `collect` (the linked collector),
// `validate` (the store validates the reply once), `evaluate` (rules, topology, explaining rows)
// and `render` (the frame bytes, with the page when one is asked for). A system run adds `join`:
// the frames of the parts become one frame, with the page of the system. The collector hands its
// typed reply to the core in the same process (AD-406), so there is no encode or decode step. When
// the scan request sets `timings`, the core writes exactly one JSON line to standard error: the
// seconds, or `refused` for a scan that was refused in whole or in a part. The frame does not
// change. The phases of the parts of a system run are summed.
/// The protocol word of the timings line.
const PROTOCOL: &str = "archkeel-core-timings-1";

/// The time of each phase of one scan, or of the sum of the parts of a system run.
#[derive(Clone, Copy, Default)]
pub(crate) struct Phases {
    pub(crate) prepare: Duration,
    pub(crate) collect: Duration,
    pub(crate) validate: Duration,
    pub(crate) evaluate: Duration,
    pub(crate) render: Duration,
    /// The join of the frames of the parts of a system run; zero for one configuration.
    pub(crate) join: Duration,
    /// The time from the read request to the end of the frame in the core, not the time of the CLI:
    /// the phases and the rest that no phase measures.
    pub(crate) wall: Duration,
}

impl Phases {
    /// The evaluation and rendering phases between the supplied monotonic times.
    pub(crate) fn evaluation(
        start: Option<Duration>,
        render: Option<Duration>,
        end: Option<Duration>,
    ) -> Phases {
        Phases {
            evaluate: render
                .zip(start)
                .map_or(Duration::ZERO, |(end, start)| end - start),
            render: end
                .zip(render)
                .map_or(Duration::ZERO, |(end, start)| end - start),
            ..Phases::default()
        }
    }

    /// The sum of two parts of one run.
    pub(crate) fn plus(self, other: Phases) -> Phases {
        Phases {
            prepare: self.prepare + other.prepare,
            collect: self.collect + other.collect,
            validate: self.validate + other.validate,
            evaluate: self.evaluate + other.evaluate,
            render: self.render + other.render,
            join: self.join + other.join,
            wall: self.wall + other.wall,
        }
    }

    /// The timings line: the phases in the order of the run, in seconds.
    pub(crate) fn line(&self) -> String {
        let seconds = |time: Duration| format!("{:.6}", time.as_secs_f64());
        format!(
            "{{\"protocol\":\"{PROTOCOL}\",\"clock\":\"monotonic\",\"unit\":\"seconds\",\
\"phases\":{{\"prepare\":{},\"collect\":{},\"validate\":{},\"evaluate\":{},\"render\":{},\"join\":{}}},\
\"core_seconds\":{}}}",
            seconds(self.prepare),
            seconds(self.collect),
            seconds(self.validate),
            seconds(self.evaluate),
            seconds(self.render),
            seconds(self.join),
            seconds(self.wall),
        )
    }

    /// The timings line of a scan that was refused in whole or in a part: no seconds.
    pub(crate) fn refused_line() -> String {
        format!("{{\"protocol\":\"{PROTOCOL}\",\"refused\":true}}")
    }
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
        explorer: Vec::new(),
        explain: None,
        rule_rationales: BTreeMap::new(),
        engine: ENGINE,
        sections: BTreeMap::new(),
        locations: BTreeMap::new(),
        collection_gaps: Vec::new(),
        contract_digest: None,
        gaps: crate::baseline_frame::gap_rows(&ruling),
        baseline: None,
        system: None,
        part_of: None,
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
        timings: None,
        timings_asked: false,
    })
}

#[cfg(test)]
#[path = "phases_tests.rs"]
mod phases_tests;

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
