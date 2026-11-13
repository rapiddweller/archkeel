// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A typed refusal on stderr is not a ruling, a frame, or partial facts (AD-420).

#[derive(Debug)]
pub(crate) enum Error {
    Request(String),
    Refused(archkeel_collect::Refusal),
}

#[derive(serde::Serialize)]
#[serde(rename_all = "snake_case")]
enum Kind {
    ParseWorkLimit,
    Unsupported,
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
                write!(
                    out,
                    "{}",
                    serde_json::json!({
                    "protocol": "archkeel-core-refusal-1",
                    "kind": kind,
                    "subject": refusal.part,
                    "reason": refusal.reason,
                    })
                )
            }
        }
    }
}
