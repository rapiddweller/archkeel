// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The script facts of one file, as typed values (AD-340, PR 4.3a-4). The fields and their order
//! are the fields of the Python dataclasses of `syntax.py`, so that the dump and a later writer
//! of the protocol produce the same values.

use crate::source::Span;

/// A member of a published object: `(published name, local name, span of its declaration)`.
pub(crate) type Member = (String, String, Span);

/// `ScriptGlobal`: a written browser-global object publication.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub(crate) struct ScriptGlobal {
    pub name: String,
    pub span: Span,
    pub members: Vec<Member>,
    pub stable: bool,
    pub source_members: Vec<Member>,
    pub source_origin: bool,
    pub availability: Vec<Span>,
}

/// `ScriptNamespace`.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub(crate) struct ScriptNamespace {
    pub name: String,
    pub span: Span,
    pub initialization: Span,
}

/// `ScriptFactoryMember`.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub(crate) struct FactoryMember {
    pub name: String,
    pub span: Span,
    pub target: Option<String>,
    pub target_span: Option<Span>,
    pub forwarded_span: Option<Span>,
    pub callable: bool,
}

/// `ScriptFactory`.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub(crate) struct ScriptFactory {
    pub name: String,
    pub span: Span,
    pub members: Vec<FactoryMember>,
}

/// `ScriptDestructure`.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub(crate) struct ScriptDestructure {
    pub span: Span,
    pub path: Vec<String>,
    pub members: Vec<Member>,
}

/// `ScriptAlias`.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub(crate) struct ScriptAlias {
    pub name: String,
    pub span: Span,
    pub reference_span: Span,
    pub path: Vec<String>,
    pub calls: Vec<Span>,
    pub factory: bool,
    pub reads: Vec<Span>,
    pub escapes: Vec<Vec<String>>,
    pub complete: bool,
}

/// A write: the published name, or `None` where the write is not known, and where it is.
pub(crate) type Write = (Option<String>, Span);

/// The phrase of a run-time key that can name `constructor`: a trojan horse whose reach a contract can
/// declare (AD-664).
pub(crate) fn key_form() -> &'static str {
    "a key that is no literal and can name constructor"
}

/// The kinds of a literal value: it is no function, so a write of it patches no call (#1674).
const LITERAL_KINDS: [&str; 7] = [
    "string",
    "number",
    "true",
    "false",
    "null",
    "undefined",
    "template_string",
];

/// The deepest value that `no_function` follows: a chain of choices or assignments this long is not read.
const NO_FUNCTION_DEPTH: usize = 16;

/// A value that can be no function, so that a write of it patches no call (AD-1470): a literal, a
/// choice between such values (`dark ? "light" : "dark"`) and an assignment of one
/// (`a = b = 64`). A value from a call, a name or a member stays a possible function.
/// `unwrap` removes the parentheses and the type wrappers of a node.
pub(crate) fn no_function<'t>(
    node: tree_sitter::Node<'t>,
    unwrap: &dyn Fn(tree_sitter::Node<'t>) -> tree_sitter::Node<'t>,
) -> bool {
    fn read<'t>(
        node: tree_sitter::Node<'t>,
        unwrap: &dyn Fn(tree_sitter::Node<'t>) -> tree_sitter::Node<'t>,
        depth: usize,
    ) -> bool {
        let node = unwrap(node);
        if LITERAL_KINDS.contains(&node.kind()) {
            return true;
        }
        let next = depth.saturating_sub(1);
        match node.kind() {
            _ if depth == 0 => false,
            "ternary_expression" => ["consequence", "alternative"].iter().all(|field| {
                node.child_by_field_name(field)
                    .is_some_and(|branch| read(branch, unwrap, next))
            }),
            "assignment_expression" => node
                .child_by_field_name("right")
                .is_some_and(|value| read(value, unwrap, next)),
            _ => false,
        }
    }
    read(node, unwrap, NO_FUNCTION_DEPTH)
}

/// A member patch of a free global (#1674): `Math.max = f` patches the path `max` of `Math`,
/// `document.body.style.x = v` the path `body.style.x`. A key that is no literal ends the path, so
/// the patch covers every member below the known part. `target` holds the line and column of each name of the
/// written target (`Math`, `max`): a use there is the write, no read of the patched value. `span`
/// is the place of the write.
#[derive(Clone)]
pub(crate) struct Patch {
    pub global: String,
    pub path: Vec<String>,
    pub target: Vec<(i64, i64)>,
    pub span: Span,
}

/// A direct form that can write any global: its place and the kind of the form (AD-540).
pub(crate) type Blocker = (Span, &'static str);

/// The script fields of `Syntax`.
#[derive(Default)]
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub(crate) struct Script {
    pub globals: Vec<ScriptGlobal>,
    pub writes: Vec<Write>,
    pub aliases: Vec<ScriptAlias>,
    pub factories: Vec<ScriptFactory>,
    pub source_writes: Vec<Write>,
    pub write_paths: Vec<Vec<String>>,
    pub top_level_write_paths: Vec<Vec<String>>,
    pub destructures: Vec<ScriptDestructure>,
    pub namespaces: Vec<ScriptNamespace>,
    /// Some node writes an unknown global through an amplifier form (AD-540).
    pub amplified: bool,
    /// The file gives the scan a host entry (AD-540).
    pub host_entry: bool,
    /// The places of the direct forms that write an unknown global, each with the kind of its form.
    pub blockers: Vec<Blocker>,
    /// A write with no path has no blocker here, so the report cannot group the gaps behind it.
    pub unlabelled_empty: bool,
    /// The line and column of each free name whose use is only read: the operand of `typeof`,
    /// `!` or a comparison, the left of `&&`, or a condition (AD-576). It builds no code.
    pub contained_reads: Vec<(i64, i64)>,
    /// The places of the amplifier forms (a window member, `this`) with the kind of the form.
    pub amp_blockers: Vec<Blocker>,
    /// The member patches of a free global (`Math.max = f`, #1674).
    pub patches: Vec<Patch>,
    /// The paths of two or more names that the file writes only with a value that is no function
    /// (AD-1470): they patch no call, so a file outside the scan roots that writes them replaces
    /// no global.
    pub plain_member_paths: Vec<Vec<String>>,
}
