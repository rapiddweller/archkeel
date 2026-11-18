// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use crate::ids::FactId;

/// The declarations and sites that the linked Python collector proves.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ConstructedCalls {
    /// Direct methods of classes with default allocation and lookup.
    pub targets: Vec<FactId>,
    /// Calls on freshly constructed instances of those classes.
    pub calls: Vec<ConstructedCall>,
}

/// The linked producer's witness for one call on a freshly constructed instance.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConstructedCall {
    /// The method call site.
    pub call: FactId,
    /// The constructor call site in the same callable.
    pub constructor: FactId,
    /// The direct instance method of the constructed class.
    pub method: FactId,
    /// The single local result binding, when the call does not use the instance directly.
    pub binding: Option<FactId>,
    /// The direct import that binds the class in a different module.
    pub import: Option<FactId>,
}

impl ConstructedCall {
    /// The source, provider, declaration and binding of a direct, unique import.
    pub fn direct_import(fact: &crate::ImportFact) -> Option<[&str; 4]> {
        let crate::ImportFact::Import(data) = fact else {
            return None;
        };
        if !data.module_level_import
            || data.under_type_checking
            || !data.symbols_known
            || data.source_binding_unique != Some(true)
        {
            return None;
        }
        Some([
            data.source_module.as_str(),
            data.target_module.as_str(),
            data.symbol.as_deref()?,
            data.binding.as_deref()?,
        ])
    }
}
