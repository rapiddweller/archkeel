// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The base of a check request (AD-399): the reply of the accepted commit of `archkeel check`.
//!
//! `check` decides the rules of the candidate under the contract at the baseline commit, and it
//! reads the accepted commit under the same contract. The rule verdicts of the run do not read the
//! base. So the core takes the base reply only to see it soundly, as the reference engine does
//! before it compares the two commits: the store must accept the reply, the trust function of the
//! request kind (`check::stage_one_shell_trust`) must trust it, its profile must be the profile of
//! the candidate, and the model of the base must derive under the contract of the request. Each
//! other result is one reason that names the whole contract, so the frame never decides the run.
//! The core takes no verdict of the base from the caller; the request carries only bytes.

use archkeel_store::Ingested;

use crate::contract::{ContractInput, ContractState};
use crate::dual_run::{self, TrustOf};
use crate::engine::{Answer, Engine};
use crate::ingest::ReplyState;
use crate::request::Request;

/// The first words of each reason of the base. The shell counts them.
pub(crate) const BASE: &str = "the base reply";

/// The base reply of a check request and the trust function of its request kind.
pub(crate) struct Base {
    pub(crate) reply: Vec<u8>,
    pub(crate) trust: TrustOf,
}

/// The inputs of the candidate that the base shares: the namespace, the contract and the roots.
pub(crate) struct Shared {
    pub(crate) namespace: String,
    pub(crate) input: ContractInput,
    pub(crate) roots: Vec<String>,
}

/// The reason that the core cannot read the base soundly, or `None`.
pub(crate) fn gap(base: Base, candidate: Option<&Ingested>, shared: Shared) -> Option<String> {
    read(base, candidate, shared)
        .err()
        .map(|why| format!("{BASE}: {why}"))
}

fn read(base: Base, candidate: Option<&Ingested>, shared: Shared) -> Result<(), String> {
    let mut engine = Engine::default();
    match engine.answer(Request::Ingest {
        reply: base.reply,
        inflate_limit: dual_run::INFLATE_LIMIT,
    }) {
        Answer::Reply(ReplyState::Ingested(_)) => {}
        Answer::Reply(ReplyState::Refused(message)) => {
            return Err(format!("the store refuses it: {message}"));
        }
        other => return Err(format!("unexpected answer {other:?}")),
    }
    let trust = (base.trust)(shared.namespace, engine.reply());
    if let Some(gap) = trust.gap {
        return Err(gap);
    }
    let profile = |reply: &Ingested| reply.reply().facts.profile.as_str();
    same_profile(engine.reply().map(profile), candidate.map(profile))?;
    let input = shared.input;
    let settings = dual_run::settings_of(trust.settings, &input, shared.roots);
    engine.answer(Request::Settings(settings));
    match engine.answer(Request::Contract(input)) {
        Answer::Contract(ContractState::Parsed(_)) => {}
        Answer::Contract(ContractState::Missing(paths)) => {
            return Err(crate::contract::missing_reason(&paths));
        }
        Answer::Contract(ContractState::Refused(message)) => {
            return Err(format!("the contract is refused: {message}"));
        }
        other => return Err(format!("unexpected answer {other:?}")),
    }
    let (_, derived) = engine.derived();
    derived
        .models()
        .map(|_| ())
        .map_err(|reason| format!("it gives no model: {reason}"))
}

/// The reference engine compares two commits of one collector only. Without a candidate reply,
/// the frame already names the reply.
fn same_profile(base: Option<&str>, candidate: Option<&str>) -> Result<(), String> {
    match (base, candidate) {
        (Some(base), Some(candidate)) if base != candidate => Err(format!(
            "its profile {base} is not the profile {candidate} of the candidate"
        )),
        _ => Ok(()),
    }
}

#[cfg(test)]
#[path = "base_tests.rs"]
mod tests;
