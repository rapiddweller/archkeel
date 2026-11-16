// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The types that a declared facade signature names (AD-580; `facade_types` of 4.0.1, AD-65).
//!
//! A `public` entry of the contract covers a function, a class or a module. The written type of
//! each parameter and return of a covered function, and of each public method of a covered class,
//! reaches every consumer of that facade whether or not an import names it. The reading uses the
//! signature shapes of AD-550 and the binding that the collector proved for each name: a name
//! with no proven binding names nothing. Each type is recorded as the name that the signature
//! writes and as the definition that the one plain import route reaches.

use std::collections::HashSet;

use archkeel_facts::type_shape::{Binding, TypeShape};

use crate::boundary_facts::{BoundaryFacts, Callable, Entry, Origin};
use crate::boundary_positions::method_name;
use crate::boundary_surface::{entries, names};
use crate::model::Model;

/// The dotted names of the types that the declared signatures of the contract of `model` name,
/// or `None` when the run has no signature shapes.
pub fn facade_types(model: &Model) -> Option<HashSet<String>> {
    let facts = model.graph().boundary()?;
    let mut found = Types {
        facts,
        names: HashSet::new(),
        seen: HashSet::new(),
    };
    for entry in entries(model, None) {
        let Ok(covered) = names(model, &entry) else {
            continue;
        };
        for name in covered {
            if let Origin::Defined(qualified, item) = facts.origin(&entry.module, &name) {
                found.entry(qualified, item);
            }
        }
    }
    Some(found.names)
}

struct Types<'a> {
    facts: &'a BoundaryFacts,
    names: HashSet<String>,
    seen: HashSet<String>,
}

impl Types<'_> {
    fn entry(&mut self, qualified: &str, entry: &Entry) {
        if !self.seen.insert(qualified.to_owned()) {
            return;
        }
        match entry {
            Entry::Callable(callable) => self.callable(callable),
            Entry::Class(class) => {
                let facts = self.facts;
                let callables =
                    class
                        .methods
                        .iter()
                        .filter_map(|method| match facts.entry(method) {
                            Some(Entry::Callable(callable)) if method_name(&callable.name) => {
                                Some(callable)
                            }
                            _ => None,
                        });
                callables.for_each(|callable| self.callable(callable));
            }
            Entry::Value => {}
        }
    }

    fn callable(&mut self, callable: &Callable) {
        for shape in callable.slots.iter().filter_map(|slot| slot.shape.as_ref()) {
            self.shape(shape);
        }
        if let Some(returns) = &callable.returns {
            self.shape(returns);
        }
    }

    fn shape(&mut self, shape: &TypeShape) {
        match shape {
            TypeShape::Named { binding, .. } => self.binding(binding),
            TypeShape::Collection { args, .. } => args.iter().for_each(|arg| self.shape(arg)),
            TypeShape::Union { arms, .. } => arms.iter().for_each(|arm| self.shape(arm)),
            TypeShape::Annotated { inner, .. } => self.shape(inner),
            TypeShape::Applied { head, args, .. } => {
                self.shape(head);
                args.iter().for_each(|arg| self.shape(arg));
            }
            _ => {}
        }
    }

    fn binding(&mut self, binding: &Binding) {
        let (Binding::Defined { target } | Binding::Imported { target }) = binding else {
            return;
        };
        self.names.insert(target.clone());
        if let Origin::Defined(qualified, _) = self.facts.origin_of(target) {
            self.names.insert(qualified.to_owned());
        }
    }
}
