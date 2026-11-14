// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The check request of the shell (AD-390): the production request kind of the core.
//!
//! The shell sends the root contract and its inside contracts, the collector reply, the scan
//! roots and the namespace of the configuration. The request has no producer, pin, profile or
//! standard library field, and `deny_unknown_fields` refuses a request that names one (exit 2).
//! The core reads the profile from the reply and takes the pinned standard library of that
//! profile.
//!
//! Trust (AD-390 point 2, lead decision L-70): the reply passes through the shell, so its
//! `code_digest` is public text that a caller can write; it is no proof. The core reaches trust
//! only through `stage_one_shell_trust`. That function checks a stale build (the reply of a
//! collector of another build), not a forgery. In stage 1 the trust root is the shell: it
//! starts only the bundled collectors whose files have their recorded digests, and the reference
//! engine decides the same run from the same reply, so a difference is an error. Stage 2 must not
//! start before the core runs the native collectors in its own process (#1095).
//!
//! The request of `archkeel check` also carries the base reply: the reply of the accepted commit
//! (AD-399). The contract of that request is the contract at the baseline commit, which the shell
//! reads from Git. The base reply goes through the same trust function (`base.rs`).
//!
//! The request then goes through the one engine path of the dual run (`dual_run::run`).

use serde::Deserialize;

use archkeel_model::{Producer, Settings};
use archkeel_store::Ingested;

use crate::base::Base;
use crate::dual_run::{self, Answered, BaseOf, InsideJson, ReplyBytes, Run, Trust};

/// The protocol of the check request.
/// Version 2 removes `baseline` and adds `base` (AD-399).
const PROTOCOL: &str = "archkeel-core-check-2";
/// The code digest of this build: the digest of each native collector of the same source. It is
/// public text, so it detects a stale build and proves no producer (AD-390).
pub(crate) const CODE_DIGEST: &str = env!("ARCHKEEL_CODE_DIGEST");
/// The first words of the reason of a reply that the core cannot verify. The shell counts it.
pub(crate) const PRODUCER_NOT_VERIFIED: &str = "producer not verified";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CheckRequest {
    // Checked before through `dual_run::decode`.
    #[serde(rename = "protocol")]
    _protocol: String,
    contract: ContractJson,
    insides: Vec<InsideJson>,
    reply: Option<ReplyBytes>,
    roots: Vec<String>,
    namespace: String,
    /// The base of `archkeel check`: the reply of the accepted commit; `None` for `report`.
    base: Option<BaseJson>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BaseJson {
    reply: ReplyBytes,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ContractJson {
    path: String,
    hex: String,
}

/// The frame of one check request. An error is a request that the core cannot read.
pub(crate) fn answer(input: &[u8]) -> Result<Answered, String> {
    let request: CheckRequest = dual_run::decode(input, PROTOCOL)?;
    let reply = dual_run::ReplyInput::bytes(
        request
            .reply
            .map(|reply| dual_run::hex(&reply.hex))
            .transpose()?,
    );
    let base = request
        .base
        .map(|base| dual_run::hex(&base.reply.hex))
        .transpose()?
        .map(|reply| -> BaseOf {
            let base = Base {
                reply,
                trust: Box::new(stage_one_shell_trust),
            };
            Box::new(move |candidate, shared| crate::base::gap(base, candidate, shared))
        });
    dual_run::run(Run {
        topology: false,
        case: "check".to_owned(),
        path: request.contract.path,
        contract: dual_run::hex(&request.contract.hex)?,
        insides: dual_run::insides(request.insides)?,
        reply,
        sections: Vec::new(),
        namespace: request.namespace,
        roots: request.roots,
        baseline: false,
        report: false,
        html: false,
        base,
        trust: Box::new(stage_one_shell_trust),
        collect: None,
        documents: None,
    })
}

/// Stage 1 trust of the shell-run bundled collector. Limit (AD-390): the shell is the trust
/// root; the digest check catches a stale build, not a forged reply.
///
/// It gives the settings of the profile of the reply. It trusts the producer only when the reply
/// names the collector of its own profile and the code digest of this core build. Any other reply
/// (another adapter, another or an empty digest) names the whole contract with
/// `PRODUCER_NOT_VERIFIED` (exit 3). Without a valid reply the frame already names the reply.
/// This is the only place where the check request reaches `Producer::Trusted`, for the reply and
/// for the base reply.
pub(crate) fn stage_one_shell_trust(namespace: String, reply: Option<&Ingested>) -> Trust {
    let Some(reply) = reply else {
        return Trust {
            settings: Settings::new(namespace, String::new(), Vec::new()),
            gap: None,
        };
    };
    let facts = &reply.reply().facts;
    let profile = facts.profile;
    let standard_library = archkeel_store::standard_library(profile)
        .into_iter()
        .map(str::to_owned)
        .collect();
    let settings = Settings::new(namespace, profile.as_str().to_owned(), standard_library);
    let adapter = &facts.adapter;
    if adapter.name == profile.as_str() && adapter.code_digest == CODE_DIGEST {
        return Trust {
            settings: settings.with_producer(Producer::Trusted),
            gap: None,
        };
    }
    Trust {
        settings,
        gap: Some(format!(
            "{PRODUCER_NOT_VERIFIED}: the reply names the adapter {} with the code digest {}, \
             and this core build has the code digest {}",
            adapter.name, adapter.code_digest, CODE_DIGEST
        )),
    }
}

#[cfg(test)]
#[path = "check_tests.rs"]
mod tests;
