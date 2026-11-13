// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The identifier characters that `ruff_python_parser` accepts and CPython refuses (AD-334).
//!
//! ruff reads an identifier with `unicode-ident` 1.0.27 (Unicode 17). Each CPython checks it with
//! its own Unicode database: 3.11 has Unicode 14, 3.12 has 15, 3.13 has 15.1 and 3.14 has 16. A
//! table holds the code point ranges that ruff accepts and the CPython of one minor version
//! refuses: `ast.parse(chr(c) + "=1")` for a first character, `ast.parse("a" + chr(c) + "=1")` for
//! a later one, on CPython 3.11.12, 3.12.10, 3.13.15 and 3.14.7. The ranges are in
//! `identifier.txt`; `build.rs` fails the build when a line of it does not parse, so the lookup
//! below never skips a range.
//! `tests/test_collector_native_python_hostile.py` compares the ends of each range with the running
//! interpreter.

/// One range a line: `<version> <start|continue> <first> <last>` (see `identifier.txt`).
const TABLE: &str = include_str!("identifier.txt");
use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{
    visitor::source_order::{self, SourceOrderVisitor, TraversalSignal},
    AnyNodeRef, Expr, Identifier, ModModule,
};
use ruff_text_size::Ranged;

struct Constants {
    work: super::work::Work,
    depth: usize,
    reason: Option<(usize, &'static str)>,
}

pub fn constant_names(module: &ModModule, minor: PyMinor) -> Option<(usize, &'static str)> {
    match minor {
        PyMinor::Py311 | PyMinor::Py312 => return None,
        PyMinor::Py313 | PyMinor::Py314 => {}
    }
    let mut check = Constants {
        work: super::work::Work::new(),
        depth: 0,
        reason: None,
    };
    check.visit_body(&module.body);
    check
        .reason
        .or_else(|| check.work.failure().map(|reason| (0, reason)))
}

impl Constants {
    fn name(&mut self, name: &str, offset: usize) {
        if self.reason.is_some() || !self.work.charge(name.len()) {
            return;
        }
        for segment in name.split('.') {
            if !self.work.charge(1) {
                break;
            }
            if matches!(segment, "True" | "False" | "None") {
                self.reason = Some((offset, "identifier field cannot represent a constant"));
                break;
            }
        }
    }
}

impl<'a> SourceOrderVisitor<'a> for Constants {
    fn enter_node(&mut self, node: AnyNodeRef<'a>) -> TraversalSignal {
        self.depth = self.depth.saturating_add(1);
        if self.depth > 1000 && self.reason.is_none() {
            self.reason = Some((
                node.start().to_usize(),
                "CPython validation depth limit exceeded",
            ));
        }
        if self.reason.is_some() || !self.work.charge(1) {
            TraversalSignal::Skip
        } else {
            TraversalSignal::Traverse
        }
    }
    fn leave_node(&mut self, _: AnyNodeRef<'a>) {
        self.depth = self.depth.saturating_sub(1);
    }
    fn visit_identifier(&mut self, name: &'a Identifier) {
        self.name(name.as_str(), name.start().to_usize());
    }
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            self.name(node.id.as_str(), node.start().to_usize());
        }
        source_order::walk_expr(self, expr);
    }
}

/// Whether CPython 3.`minor` refuses `c` in an identifier that ruff accepts: `first` for the first
/// character of the name. Only a name with a character outside ASCII comes here.
pub fn refused(minor: PyMinor, first: bool, c: char) -> bool {
    let version = match minor {
        PyMinor::Py311 => "3.11",
        PyMinor::Py312 => "3.12",
        PyMinor::Py313 => "3.13",
        PyMinor::Py314 => "3.14",
    };
    let kind = if first { "start" } else { "continue" };
    let code = u32::from(c);
    TABLE.lines().any(|line| {
        let fields: Vec<&str> = line.split(' ').collect();
        let [found, found_kind, low, high] = fields.as_slice() else {
            return false;
        };
        let range = |field: &str| u32::from_str_radix(field, 16).ok();
        *found == version
            && *found_kind == kind
            && range(low).is_some_and(|low| low <= code)
            && range(high).is_some_and(|high| code <= high)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_identifier_walk_charges_nodes_names_and_dotted_segments() {
        let tree = crate::test_tree("import alpha.beta as gamma", 14).unwrap();
        let mut check = Constants {
            work: super::super::work::Work::new(),
            depth: 0,
            reason: None,
        };
        check.visit_body(&tree.body);
        assert_eq!(check.reason, None);
        assert_eq!(check.work.used(), 20);
    }
}
