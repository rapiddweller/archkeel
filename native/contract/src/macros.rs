// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declaration macros of the typed contract and the text trait that they implement.

/// A text value that only this crate can make.
pub(crate) trait Wrap {
    fn wrap(text: String) -> Self;
}

impl Wrap for String {
    fn wrap(text: String) -> Self {
        text
    }
}

/// Wrap each text.
pub(crate) fn wrap_all<T: Wrap>(texts: Vec<String>) -> Vec<T> {
    texts.into_iter().map(T::wrap).collect()
}

/// Declare a text newtype with a read accessor and no public constructor. The call passes the
/// visibility of the inner text (the crate), so the definition names no `crate` that the scan
/// cannot place.
macro_rules! text_type {
    ($inner:vis, $(#[$meta:meta])* $name:ident) => {
        $(#[$meta])*
        #[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, ::serde::Serialize)]
        pub struct $name($inner String);

        impl $name {
            /// The text of the value.
            pub fn as_text(&self) -> &str {
                &self.0
            }
        }

        impl $crate::macros::Wrap for $name {
            fn wrap(text: String) -> $name {
                $name(text)
            }
        }

    };
}

/// Declare a struct with fields of the visibility that the call passes (the crate) and a public
/// read accessor for each field. It serializes in the order of its fields: the canonical order.
/// A field attribute (a document or a serde skip) applies to the field only.
macro_rules! record {
    ($inner:vis, $(#[$meta:meta])* $name:ident { $($(#[$field_meta:meta])* $field:ident: $kind:ty),* $(,)? }) => {
        $(#[$meta])*
        #[derive(Clone, Debug, PartialEq, Eq, ::serde::Serialize)]
        pub struct $name {
            $($(#[$field_meta])* $inner $field: $kind),*
        }

        impl $name {
            $(
                pub fn $field(&self) -> &$kind {
                    &self.$field
                }
            )*
        }
    };
}

/// Declare a closed enum whose words are the snake case names of its variants.
macro_rules! closed_enum {
    ($(#[$meta:meta])* $name:ident { $($(#[$variant_meta:meta])* $variant:ident),* $(,)? }) => {
        $(#[$meta])*
        #[derive(Clone, Copy, Debug, PartialEq, Eq, ::serde::Serialize, ::serde::Deserialize)]
        #[serde(rename_all = "snake_case")]
        pub enum $name {
            $($(#[$variant_meta])* $variant),*
        }
    };
}
