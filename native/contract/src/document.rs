// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The whole parsed contract.

use crate::model::{Component, ContractDigest};
use crate::model_declarations::Declarations;
use crate::rule::Rule;
use crate::version::ContractVersion;

record!(
    pub(crate),
    /// One parsed contract. Its digest is the SHA-256 of the bytes: the contract identity of a run.
    Contract {
        version: ContractVersion,
        schema: Option<String>,
        components: Vec<Component>,
        rules: Vec<Rule>,
        declarations: Option<Declarations>,
        digest: ContractDigest,
    }
);
