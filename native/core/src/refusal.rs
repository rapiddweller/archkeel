// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A typed refusal on stderr is not a ruling, a frame, or partial facts (AD-420).

#[derive(Debug)]
pub(crate) enum Error {
    Request(String),
    Refused(archkeel_collect::Refusal),
}

/// The protocol word of the refusal on stderr: the one version.
#[derive(serde::Serialize, schemars::JsonSchema)]
enum Protocol {
    #[serde(rename = "archkeel-core-refusal-1")]
    V1,
}

#[derive(serde::Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
enum Kind {
    ParseWorkLimit,
    Unsupported,
}

/// The one typed refusal that the core writes on stderr; the shell reads it against the schema
/// generated from this type (`frame_schema::refusal_schema`).
#[derive(serde::Serialize, schemars::JsonSchema)]
pub(crate) struct Refusal<'a> {
    protocol: Protocol,
    kind: Kind,
    subject: &'a str,
    reason: &'a str,
}

impl From<String> for Error {
    fn from(reason: String) -> Self {
        Self::Request(reason)
    }
}

impl std::fmt::Display for Error {
    fn fmt(&self, out: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Request(reason) => write!(out, "archkeel-core: {reason}"),
            Self::Refused(refusal) => {
                let kind = match refusal.kind {
                    archkeel_collect::RefusalKind::ParseWork => Kind::ParseWorkLimit,
                    archkeel_collect::RefusalKind::Unsupported => Kind::Unsupported,
                };
                let line = serde_json::to_string(&Refusal {
                    protocol: Protocol::V1,
                    kind,
                    subject: refusal.part,
                    reason: &refusal.reason,
                })
                .map_err(|_| std::fmt::Error)?;
                out.write_str(&line)
            }
        }
    }
}
