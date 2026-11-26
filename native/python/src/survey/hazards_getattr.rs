// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The literal `getattr` read of a name (AD-530), split from `hazards.rs` for its size.

use ruff_python_ast::visitor::Visitor;
use ruff_python_ast::Expr;

use super::{comprehension, first_hazard, Walk, TROJAN_HORSE_STRINGS};

/// `getattr(name, "attr")` and `getattr(name, "attr", default)` with a literal attribute that
/// is no trojan horse string read the one attribute `name.attr` (AD-530). Other forms: as before.
pub(super) fn read(walk: &mut Walk, call: &ruff_python_ast::ExprCall) -> bool {
    let args = &call.arguments.args;
    let named = matches!(&*call.func, Expr::Name(f) if f.id.as_str() == "getattr");
    let (Some(Expr::Name(root)), Some(Expr::StringLiteral(attr))) = (args.first(), args.get(1))
    else {
        return false;
    };
    let literal = !TROJAN_HORSE_STRINGS.contains(&attr.value.to_str())
        && !comprehension::reflective(attr.value.to_str(), false);
    let plain = named && literal && (2..=3).contains(&args.len());
    if !plain
        || !call.arguments.keywords.is_empty()
        || walk.local("getattr")
        || walk.getattr_bound
        || walk.bound.contains_key("getattr")
    {
        return false;
    }
    let id = root.id.as_str();
    if !walk.local(id) {
        let first = |origin: String| first_hazard(origin, &[attr.value.to_str()]);
        if let Some((kind, name)) = walk.origins(id).into_iter().find_map(first) {
            walk.push(kind, &name, call);
        }
    }
    args.iter().skip(2).for_each(|item| walk.visit_expr(item));
    true
}
