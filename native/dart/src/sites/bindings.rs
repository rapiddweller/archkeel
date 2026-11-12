// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The bindings of `analyzer/dart/parse.py`: `_binding_sites`, `_local_initializer`,
//! `_canonical_local_initializer` and `_typed_receiver_names`.

use std::collections::HashSet;

use tree_sitter::Node;

use super::canonical::canonical_range;
use super::scopes::callable_decl_name;
use crate::parameters::{annotation_before, parameter};
use crate::syntax::{
    Context, Definition, DefinitionKind, MemberKind, ParameterKind, Site, SiteKind, SiteUse,
};
use crate::tree::{named, named_all, named_children, walk_with_path, Source, Work};

const CLASSIFIERS: [DefinitionKind; 5] = [
    DefinitionKind::Class,
    DefinitionKind::Interface,
    DefinitionKind::Mixin,
    DefinitionKind::Enum,
    DefinitionKind::ExtensionType,
];

/// The source of the binding sites of one node.
pub(crate) struct Binder<'a, 't> {
    pub(crate) root: Node<'t>,
    pub(crate) source: &'a Source<'a>,
    pub(crate) work: &'a Work<'t>,
}

impl<'t> Binder<'_, 't> {
    /// `_binding_sites`. `nested` is true when a `formal_parameter` is an ancestor of `node`.
    pub(crate) fn sites(&self, node: Node<'t>, nested: bool, context: &Context) -> Vec<Site> {
        match node.kind() {
            "local_function_declaration" => {
                self.local_function(node, context).into_iter().collect()
            }
            "local_variable_declaration" => self.local_variables(node, context),
            "formal_parameter" if !nested => self.formal_parameter(node, context),
            _ => Vec::new(),
        }
    }

    fn local_function(&self, node: Node<'t>, context: &Context) -> Option<Site> {
        let mut signature = None;
        walk_with_path(node, |item, _| {
            self.work.charge(1);
            if item.kind() == "function_signature" {
                signature = Some(item);
            }
            signature.is_none()
        });
        let name = callable_decl_name(signature?)?;
        context.span.as_ref()?;
        let text = self.source.text(name);
        let mut site = Site::new(
            SiteKind::Binding,
            self.source.text(node),
            self.source.span(node),
            context,
        );
        site.name = Some(text.clone());
        site.assigned_name = Some(text);
        Some(site)
    }

    fn local_variables(&self, node: Node<'t>, context: &Context) -> Vec<Site> {
        let children = named_children(node);
        self.work.charge(children.len());
        let source = self.source;
        children
            .into_iter()
            .filter(|child| child.kind() == "initialized_variable_definition")
            .filter_map(|child| {
                let name = named(child, "name")?;
                let text = source.text(name);
                let mut site = Site::new(
                    SiteKind::Binding,
                    source.text(child),
                    source.span(child),
                    context,
                );
                site.name = Some(text.clone());
                site.assigned_name = Some(text);
                site.initializer = local_initializer(child, source);
                site.initializer_source = self.canonical_local_initializer(child);
                site.assignment_annotation = annotation_before(child, name, source);
                Some(site)
            })
            .collect()
    }

    /// `_canonical_local_initializer`.
    fn canonical_local_initializer(&self, node: Node<'t>) -> Option<String> {
        let value = named(node, "value")?;
        let selectors = named_all(Some(node), "selector");
        let end = selectors.last().map_or(value.end_byte(), Node::end_byte);
        Some(canonical_range(
            self.root,
            self.source,
            self.work,
            value.start_byte(),
            end,
        ))
    }

    fn formal_parameter(&self, node: Node<'t>, context: &Context) -> Vec<Site> {
        let source = self.source;
        let parameter = parameter(node, ParameterKind::Positional, source);
        let mut binding = Site::new(
            SiteKind::Binding,
            source.text(node),
            source.span(node),
            context,
        );
        binding.name = Some(parameter.name.clone());
        binding.assignment_annotation = parameter.annotation;
        binding.initializer = parameter.default;
        let mut sites = vec![binding];
        if parameter.field_formal || parameter.super_formal {
            let kind = if parameter.field_formal {
                SiteKind::FieldFormal
            } else {
                SiteKind::SuperFormal
            };
            let mut formal = Site::new(kind, source.text(node), source.span(node), context);
            formal.name = Some(parameter.name);
            formal.r#use = SiteUse::Type;
            sites.push(formal);
        }
        sites
    }
}

/// `_local_initializer`: the value and the text of each selector after it.
fn local_initializer<'t>(node: Node<'t>, source: &Source<'_>) -> Option<String> {
    let value = named(node, "value")?;
    let mut text = source.text(value);
    for selector in named_all(Some(node), "selector") {
        text.push_str(&source.text(selector));
    }
    Some(text)
}

/// `_typed_receiver_names`: the names whose type the source writes, so a member access on them
/// is a typed receiver.
pub(crate) fn typed_receiver_names<'t>(
    root: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
    definitions: &[Definition],
) -> HashSet<String> {
    let mut names = HashSet::new();
    for definition in definitions {
        for member in &definition.members {
            if member.kind == MemberKind::Field && member.annotation.is_some() {
                names.insert(member.name.clone());
            }
        }
    }
    for definition in definitions {
        if CLASSIFIERS.contains(&definition.kind) {
            names.insert(definition.name.clone());
        }
    }
    for definition in definitions {
        let members = definition
            .members
            .iter()
            .flat_map(|member| &member.parameters);
        for parameter in definition.parameters.iter().chain(members) {
            if parameter.annotation.is_some() {
                names.insert(parameter.name.clone());
            }
        }
    }
    // Python walks the tree of each local variable declaration; a set needs each definition
    // below one of them only once.
    walk_with_path(root, |node, path| {
        work.charge(1);
        match node.kind() {
            "initialized_variable_definition" => {
                work.charge(path.len());
                names.extend(local_annotated_name(node, path, source));
            }
            "formal_parameter" => {
                let parameter = parameter(node, ParameterKind::Positional, source);
                if parameter.annotation.is_some() {
                    names.insert(parameter.name);
                }
            }
            _ => {}
        }
        true
    });
    names
}

/// The name of a definition below a local variable declaration, when it has an annotation.
fn local_annotated_name<'t>(
    node: Node<'t>,
    path: &[Node<'t>],
    source: &Source<'_>,
) -> Option<String> {
    let local = path
        .iter()
        .any(|item| item.kind() == "local_variable_declaration");
    let name = named(node, "name").filter(|_| local)?;
    annotation_before(node, name, source)?;
    Some(source.text(name))
}
