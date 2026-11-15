// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The one UML Target of a contract tree: `declared_tree_graph` of `ir/target_graph.py` at
//! release 4.0.1 joins the entities, the relationships and the scopes of the root and of each
//! mount. The ids of a mount are in the scope of its parent already (`policy::scope`), so the
//! parts do not collide.

use crate::model_uml::Target;

/// The target that holds each part in order, or `None` without a part. The schema version is the
/// one of the first part.
pub fn merge_targets(parts: &[&Target]) -> Option<Target> {
    let (first, rest) = parts.split_first()?;
    let mut merged = (*first).clone();
    for part in rest {
        merged.entities.extend(part.entities.iter().cloned());
        merged
            .relationships
            .extend(part.relationships.iter().cloned());
        merged.scopes.extend(part.scopes.iter().cloned());
    }
    Some(merged)
}
