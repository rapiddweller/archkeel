// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `_sites` of `analyzer/dart/parse.py`: the lexical sites of one source with their scope. One
//! walk keeps the ancestors of each node; it holds for each ancestor the facts that Python reads
//! with `_ancestors` for each node, so the work does not grow with the depth for each node.

mod bindings;
mod calls;
mod canonical;
mod contain;
mod references;
mod scopes;

use std::collections::HashSet;

use tree_sitter::Node;

use crate::syntax::{Context, Definition, Directive, Site};
use crate::tree::{named_children, walk_with_path, Gap, Source, Work};
use bindings::{typed_receiver_names, Binder};
use calls::expression_site;
use references::{reference_sites, Names};
use scopes::{Scopes, CONSTRUCTORS};

const DIRECTIVES: [&str; 4] = [
    "import_or_export",
    "library_name",
    "part_directive",
    "part_of_directive",
];
const PARAMETER_OWNERS: [&str; 2] = ["function_signature", "function_expression"];
const SIGNATURES: [&str; 4] = [
    "function_signature",
    "method_signature",
    "getter_signature",
    "setter_signature",
];

fn is_parameter_owner(kind: &str) -> bool {
    PARAMETER_OWNERS.contains(&kind) || CONSTRUCTORS.contains(&kind)
}

fn is_signature(kind: &str) -> bool {
    SIGNATURES.contains(&kind) || CONSTRUCTORS.contains(&kind)
}

/// The facts of one ancestor and of the ancestors above it.
#[derive(Clone, Copy, Default)]
struct Level {
    /// A directive node is this ancestor or above it: `_inside_directive`.
    directive: bool,
    /// A function expression is this ancestor or above it: `_inside_function_expression`.
    closure: bool,
    /// The outermost `formal_parameter` up to this ancestor.
    parameter: Option<usize>,
    /// The innermost `_parameter_context` owner up to this ancestor.
    owner: Option<usize>,
    /// The innermost signature up to this ancestor, the first loop of `_callable_context`.
    signature: Option<usize>,
}

impl Level {
    fn below<'t>(above: Self, node: Node<'t>, at: usize) -> Self {
        let kind = node.kind();
        Self {
            directive: above.directive || DIRECTIVES.contains(&kind),
            closure: above.closure || kind == "function_expression",
            parameter: above
                .parameter
                .or((kind == "formal_parameter").then_some(at)),
            owner: if is_parameter_owner(kind) {
                Some(at)
            } else {
                above.owner
            },
            signature: if is_signature(kind) {
                Some(at)
            } else {
                above.signature
            },
        }
    }
}

/// The work limit of the sites of a source of `size` bytes: linear in the size, and far above
/// each measured source (AD-376).
pub(crate) fn work_limit(size: usize) -> u64 {
    let size = u64::try_from(size).unwrap_or(u64::MAX);
    size.saturating_mul(WORK_PER_BYTE).saturating_add(WORK_BASE)
}

/// The work for each byte of the source, and the work that each source gets.
const WORK_PER_BYTE: u64 = 64;
const WORK_BASE: u64 = 1 << 24;

/// `_sites(root, source, definitions, directives)`, or a gap when the work passes the limit or
/// the walk meets a state that a Tree-sitter tree cannot have.
pub(crate) fn sites<'t>(
    root: Node<'t>,
    source: &Source<'_>,
    definitions: &[Definition],
    directives: &[Directive],
    work: &Work<'t>,
) -> Result<Vec<Site>, Gap> {
    let receivers = typed_receiver_names(root, source, work, definitions);
    let prefixes: HashSet<String> = directives
        .iter()
        .filter_map(|item| item.prefix.clone())
        .collect();
    let names = Names {
        receivers: &receivers,
        prefixes: &prefixes,
    };
    let mut scopes = Scopes::new(root, source, work)?;
    let binder = Binder { root, source, work };
    let mut levels: Vec<Level> = Vec::new();
    let mut signature_children: Vec<Option<Vec<Node<'t>>>> = Vec::new();
    let mut result: Vec<Site> = Vec::new();
    let mut failure: Option<Gap> = None;
    walk_with_path(root, |node, path| {
        work.charge(1);
        if work.exceeded() {
            failure = Some(Gap("the work passes the limit of the site walks"));
            return false;
        }
        levels.truncate(path.len());
        signature_children.truncate(path.len());
        while let Some(parent) = path.get(levels.len()) {
            let above = levels.last().copied().unwrap_or_default();
            levels.push(Level::below(above, *parent, levels.len()));
            signature_children.push(None);
        }
        let step = Step {
            node,
            path,
            levels: &levels,
            scopes: &mut scopes,
            source,
            work,
        };
        match step.sites(&mut signature_children, &binder, &names) {
            Ok(found) => {
                result.extend(found);
                true
            }
            Err(gap) => {
                failure = Some(gap);
                false
            }
        }
    });
    if let Some(gap) = failure {
        return Err(gap);
    }
    result.sort_by(|a, b| {
        (a.span.start_byte, a.kind.as_str()).cmp(&(b.span.start_byte, b.kind.as_str()))
    });
    Ok(result)
}

/// The body of the loop of `_sites` for one node.
struct Step<'s, 't> {
    node: Node<'t>,
    path: &'s [Node<'t>],
    levels: &'s [Level],
    scopes: &'s mut Scopes<'t>,
    source: &'s Source<'s>,
    work: &'s Work<'t>,
}

impl<'t> Step<'_, 't> {
    fn sites(
        mut self,
        signature_children: &mut [Option<Vec<Node<'t>>>],
        binder: &Binder<'_, 't>,
        names: &Names<'_>,
    ) -> Result<Vec<Site>, Gap> {
        let here = self.levels.last().copied().unwrap_or_default();
        // The scope query must see each node in walk order, also a node inside a directive.
        let (count, innermost) = self.scopes.active(self.node)?;
        if here.directive {
            return Ok(Vec::new());
        }
        let scope = innermost.and_then(|k| self.scopes.list.get(k));
        let mut context = Context {
            scope: scope.and_then(|scope| scope.name.clone()),
            span: scope.map(|scope| self.source.span(scope.node)),
            depth: count,
        };
        let is_parameter = self.node.kind() == "formal_parameter";
        let parameter = if is_parameter {
            Some(self.path.len())
        } else {
            here.parameter
        };
        if let Some(at) = parameter {
            if let Some(found) = self.parameter_context(at, here)? {
                context = found;
            }
        } else if scope.is_none() {
            if let Some(found) = self.callable_context(here, signature_children)? {
                context = found;
            }
        }
        let closure = here.closure;
        let mut found = binder.sites(self.node, here.parameter.is_some(), &context);
        found.extend(expression_site(
            self.node,
            self.path,
            binder.root,
            self.source,
            self.work,
            &context,
        ));
        found.extend(reference_sites(
            self.node,
            self.path,
            self.source,
            self.work,
            &context,
            names,
        ));
        for site in &mut found {
            site.closure_scope = closure;
            // A site copies the text of its node: a nest of calls copies the source once for
            // each level, so the text counts as work.
            self.work.charge(site.expression.len());
        }
        Ok(found)
    }

    /// `_parameter_context` of the parameter at `at` in the path; `at` is the length of the path
    /// for the node itself.
    fn parameter_context(&mut self, at: usize, here: Level) -> Result<Option<Context>, Gap> {
        // The facts of the ancestors of the parameter: the level just above it.
        let above = at
            .checked_sub(1)
            .and_then(|index| self.levels.get(index))
            .copied();
        let above = if at == self.path.len() {
            Some(here)
        } else {
            above
        };
        let Some(above) = above else {
            return Ok(None);
        };
        if above.parameter.is_some() {
            return Ok(None);
        }
        let Some(owner) = above.owner else {
            return Ok(None);
        };
        let callable = *self
            .path
            .get(owner)
            .ok_or(Gap("an owner is out of the path"))?;
        let ancestors = self.path.get(..owner).unwrap_or_default();
        self.scopes
            .context_for(callable, ancestors, self.source, self.work)
            .map(Some)
    }

    /// `_callable_context`: the innermost signature ancestor, else the first signature child of
    /// an ancestor that starts at or before the node.
    fn callable_context(
        &mut self,
        here: Level,
        signature_children: &mut [Option<Vec<Node<'t>>>],
    ) -> Result<Option<Context>, Gap> {
        if let Some(at) = here.signature {
            let callable = *self
                .path
                .get(at)
                .ok_or(Gap("a signature is out of the path"))?;
            let ancestors = self.path.get(..at).unwrap_or_default();
            return self
                .scopes
                .context_for(callable, ancestors, self.source, self.work)
                .map(Some);
        }
        for (at, ancestor) in self.path.iter().enumerate().rev() {
            self.work.charge(1);
            let slot = signature_children
                .get_mut(at)
                .ok_or(Gap("a level is missing"))?;
            let candidates = slot.get_or_insert_with(|| {
                let all = named_children(*ancestor);
                self.work.charge(all.len());
                all.into_iter()
                    .filter(|child| is_signature(child.kind()))
                    .collect()
            });
            let node = self.node;
            let found = candidates.iter().find(|child| {
                child.start_byte() <= node.start_byte() && node.end_byte() <= ancestor.end_byte()
            });
            if let Some(callable) = found.copied() {
                let ancestors = self.path.get(..=at).unwrap_or_default();
                return self
                    .scopes
                    .context_for(callable, ancestors, self.source, self.work)
                    .map(Some);
            }
        }
        Ok(None)
    }
}

#[cfg(test)]
#[path = "sites_tests.rs"]
mod tests;
