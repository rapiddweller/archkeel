// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Ingest` request: the store validates the collector reply once.

use archkeel_store::Ingested;

/// What the engine knows of the reply.
#[derive(Debug)]
pub(crate) enum ReplyState {
    /// Valid: its file count.
    Ingested(usize),
    /// The store refused the reply.
    Refused(String),
}

/// The state of the reply, and the reply when the store accepts it.
#[cfg(any(test, feature = "harness"))]
pub(crate) fn answer(reply: &[u8], inflate_limit: u64) -> (ReplyState, Option<Ingested>) {
    // The byte door of the harness runs the checks of the collector too (AD-688), as the scan does.
    let validated = archkeel_store::ingest_reply(reply, inflate_limit)
        .and_then(|ingested| archkeel_collect::check(&ingested.reply().facts).map(|()| ingested));
    collected(validated)
}

/// The state of a reply that the store validated or refused: the bytes of a request, or the
/// typed reply of the collector in the core process (AD-406). Both doors of the store run the
/// same validation, so the two give the same state for the same facts.
pub(crate) fn collected(validated: Result<Ingested, String>) -> (ReplyState, Option<Ingested>) {
    match validated {
        Ok(ingested) => {
            let files = ingested.reply().facts.files.len();
            (ReplyState::Ingested(files), Some(ingested))
        }
        Err(message) => (ReplyState::Refused(message), None),
    }
}
