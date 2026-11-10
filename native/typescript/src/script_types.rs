// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The script facts of one file, as typed values (AD-340, PR 4.3a-4). The fields and their order
//! are the fields of the Python dataclasses of `syntax.py`, so that the dump and a later writer
//! of the protocol produce the same values.

use crate::source::Span;

/// A member of a published object: `(published name, local name, span of its declaration)`.
pub type Member = (String, String, Span);

/// `ScriptGlobal`: a written browser-global object publication.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct ScriptGlobal {
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
pub struct ScriptNamespace {
    pub name: String,
    pub span: Span,
    pub initialization: Span,
}

/// `ScriptFactoryMember`.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct FactoryMember {
    pub name: String,
    pub span: Span,
    pub target: Option<String>,
    pub target_span: Option<Span>,
    pub forwarded_span: Option<Span>,
    pub callable: bool,
}

/// `ScriptFactory`.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct ScriptFactory {
    pub name: String,
    pub span: Span,
    pub members: Vec<FactoryMember>,
}

/// `ScriptDestructure`.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct ScriptDestructure {
    pub span: Span,
    pub path: Vec<String>,
    pub members: Vec<Member>,
}

/// `ScriptAlias`.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct ScriptAlias {
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
pub type Write = (Option<String>, Span);

/// The script fields of `Syntax`.
#[derive(Default)]
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct Script {
    pub globals: Vec<ScriptGlobal>,
    pub writes: Vec<Write>,
    pub aliases: Vec<ScriptAlias>,
    pub factories: Vec<ScriptFactory>,
    pub source_writes: Vec<Write>,
    pub write_paths: Vec<Vec<String>>,
    pub top_level_write_paths: Vec<Vec<String>>,
    pub destructures: Vec<ScriptDestructure>,
    pub namespaces: Vec<ScriptNamespace>,
}
