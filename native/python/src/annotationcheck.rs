// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Type parameters and lazy annotations enter their own compiler scope.

use super::Check;
use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{visitor::Visitor, Expr, TypeParam, TypeParams};
use std::collections::HashSet;

impl Check<'_> {
    pub(super) fn annotation(&mut self, expr: &Expr) {
        let restricted = match self.minor {
            PyMinor::Py311 | PyMinor::Py312 | PyMinor::Py313 => false,
            PyMinor::Py314 => true,
        };
        let old = self.restricted;
        self.restricted |= restricted;
        self.visit_expr(expr);
        self.restricted = old;
    }

    pub(super) fn type_parameters(&mut self, params: Option<&TypeParams>) {
        let Some(params) = params else {
            return;
        };
        let old = std::mem::replace(&mut self.restricted, true);
        let mut names = HashSet::new();
        let mut default_seen = false;
        for param in &params.type_params {
            if !self.work.charge(1) {
                break;
            }
            if param.name().as_str() == "__debug__" {
                self.fail(param, "cannot bind __debug__");
            }
            if !names.insert(param.name().as_str()) {
                self.fail(param, "duplicate type parameter");
            }
            if let TypeParam::TypeVar(var) = param {
                if let Some(bound) = &var.bound {
                    self.visit_expr(bound);
                }
            }
            let default = param.default();
            if default.is_none() && default_seen {
                self.fail(param, "non-default type parameter follows a default");
            }
            default_seen |= default.is_some();
            if let Some(default) = default {
                match self.minor {
                    PyMinor::Py311 | PyMinor::Py312 => {
                        self.fail(param, "type parameter defaults require Python 3.13");
                    }
                    PyMinor::Py313 | PyMinor::Py314 => self.visit_expr(default),
                }
            }
        }
        self.restricted = old;
    }
}
