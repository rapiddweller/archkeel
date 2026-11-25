// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A vendored crate: the coercions to `dyn` happen here, and no body of the workspace shows them.

use std::any::Any;

/// Erases a value to `dyn Any`.
pub fn erase_any<T: Any>(value: T) -> Box<dyn Any> {
    Box::new(value)
}

/// Erases a value to `dyn Send`.
pub fn erase_send<T: Send + 'static>(value: T) -> Box<dyn Send> {
    Box::new(value)
}

/// A trait with a blanket impl that erases to `dyn Any`.
pub trait Erase {
    /// Erases the value.
    fn erase(self) -> Box<dyn Any>;
}

impl<T: Any> Erase for T {
    fn erase(self) -> Box<dyn Any> {
        Box::new(self)
    }
}

/// A plugin.
pub trait Plugin {
    /// Runs the plugin.
    fn go(&self);
}

/// Keeps plugins.
#[derive(Default)]
pub struct Registry {
    items: Vec<Box<dyn Plugin>>,
}

impl Registry {
    /// Keeps a plugin: the coercion to `dyn Plugin` is here.
    pub fn register<T: Plugin + 'static>(&mut self, plugin: T) {
        self.items.push(Box::new(plugin));
    }

    /// Runs each plugin.
    pub fn run_all(&self) {
        self.items.iter().for_each(|item| item.go());
    }
}
