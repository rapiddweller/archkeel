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

pub(super) const ENGINE: &str = concat!("archkeel-core ", env!("ARCHKEEL_CODE_DIGEST"));

#[derive(Serialize)]
pub(super) struct Parts {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) topology: Option<crate::topology_projection::Topology>,
    pub(super) engine: &'static str,
    pub(super) sections: BTreeMap<&'static str, Vec<serde_json::Value>>,
    pub(super) unsupported: UnsupportedParts,
    pub(super) self_test: SelfTest,
    pub(super) locations: BTreeMap<String, Location>,
    pub(super) collection_gaps: Vec<CollectionGap>,
    pub(super) contract_digest: Option<String>,
}

#[derive(Serialize)]
pub(super) struct CollectionGap {
    kind: String,
    subjects: Vec<String>,
    reason: String,
    evidence: Vec<String>,
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
        })
        .collect()
}

#[derive(Serialize)]
pub(super) struct Location {
    path: String,
    line: i64,
}

#[derive(Serialize)]
pub(super) struct UnsupportedParts {
    pub(super) sections: BTreeMap<&'static str, String>,
    pub(super) report: Option<String>,
}

#[derive(Serialize)]
pub(super) struct SelfTest {
    pub(super) contract: ContractCheck,
    pub(super) reply: ReplyCheck,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) collect: Option<serde_json::Value>,
}

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum ContractCheck {
    Rules(BTreeMap<String, RuleKind>),
    Missing(Vec<String>),
    Refused(String),
    NotRead(String),
}

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum ReplyCheck {
    Files(usize),
    Refused(String),
    Absent(String),
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
            ..Named::default()
        },
    )
    .map_err(|error| error.to_string())?;
    let parts = Parts {
        topology: None,
        engine: ENGINE,
        sections: BTreeMap::new(),
        locations: BTreeMap::new(),
        collection_gaps: Vec::new(),
        contract_digest: None,
        unsupported: UnsupportedParts {
            sections: BTreeMap::new(),
            report: None,
        },
        self_test: SelfTest {
            contract: ContractCheck::NotRead(reason.to_owned()),
            reply: ReplyCheck::Absent(reason.to_owned()),
            collect: Some(serde_json::json!({"refused": reason})),
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
    use super::*;

    #[test]
    fn a_contract_location_has_the_citation_and_line_of_its_settings() {
        for (bytes, line) in [(b"{}\n".as_slice(), 1), (b"\n{}\n".as_slice(), 0)] {
            let settings = Settings::new(String::new(), String::new(), Vec::new())
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
