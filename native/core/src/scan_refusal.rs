// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A refused collection has no contract input. Never parse empty bytes as a contract.

use super::{
    Answered, BTreeMap, ContractCheck, Named, Parts, Reason, ReplyCheck, SelfTest,
    UnsupportedParts, ENGINE,
};

pub(crate) fn refused_scan(reason: &str) -> Result<Answered, String> {
    let missing = Reason::MissingInput(archkeel_model::Input::Reply);
    let ruling = archkeel_report::rule(
        Err(&missing),
        Named {
            contract: Some(reason.to_owned()),
            ..Named::default()
        },
    )
    .map_err(|error| error.to_string())?;
    let parts = Parts {
        engine: ENGINE,
        sections: BTreeMap::new(),
        locations: BTreeMap::new(),
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
        .frame(&parts)
        .map_err(|error| error.to_string())?
        .into_bytes();
    Ok(Answered {
        frame,
        names_a_gap: true,
    })
}
