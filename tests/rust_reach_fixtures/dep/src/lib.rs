// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A plugin registry: the cast to `dyn Plugin` happens in a generic function that no body of `ws` holds.

use std::sync::Mutex;

/// A plugin.
pub trait Plugin: Send {
    /// Runs the plugin.
    fn hit(&self);
}

static REGISTRY: Mutex<Vec<Box<dyn Plugin>>> = Mutex::new(Vec::new());

/// Keeps a plugin. The coercion to `dyn Plugin` is here.
pub fn register<T: Plugin + 'static>(plugin: T) {
    REGISTRY.lock().unwrap().push(Box::new(plugin));
}

/// Gives a registered plugin back.
pub fn take() -> Option<Box<dyn Plugin>> {
    REGISTRY.lock().unwrap().pop()
}

/// Erases a value to `dyn Send` inside this crate: no body of the workspace shows the coercion.
pub fn erase_send<T: Send + 'static>(value: T) -> Box<dyn Send> {
    Box::new(value)
}

/// Erases a value to `dyn Any` inside this crate: no body of the workspace shows the coercion.
pub fn erase_any<T: std::any::Any>(value: T) -> Box<dyn std::any::Any> {
    Box::new(value)
}

/// A trait of a dependency whose impl erases a value to `dyn Any`: the call from the workspace names the
/// trait item, and the body that runs is in this crate.
pub trait Eraser {
    /// Erases the value.
    fn erase_with<T: std::any::Any>(value: T) -> Box<dyn std::any::Any>;
}

/// The impl of `Eraser`.
pub struct Hold;

impl Eraser for Hold {
    fn erase_with<T: std::any::Any>(value: T) -> Box<dyn std::any::Any> {
        Box::new(value)
    }
}

/// A function with an unbounded parameter: it can only move and drop the value.
pub fn consume<T>(_value: T) {}

/// `'static` is a bound: each `'static` type is `Any`.
pub fn keep_static<T: 'static>(value: T) -> Box<dyn std::any::Any> {
    Box::new(value)
}

/// An auto trait and a lifetime are bounds too.
pub fn keep_send<'a, T: Send + 'a>(value: T) -> Box<dyn Send + 'a> {
    Box::new(value)
}

/// A type whose parameter is unbounded, and a trait that its impl erases through (the bound is on the impl).
pub struct Wrapper<T>(pub T);

/// A trait of this crate.
pub trait Erase {
    /// Erases the value to `dyn Any`.
    fn erase(self) -> Box<dyn std::any::Any>;
}

impl<T: 'static> Erase for Wrapper<T> {
    fn erase(self) -> Box<dyn std::any::Any> {
        Box::new(self.0)
    }
}

/// The bound is on an associated type of the parameter.
pub fn first_any<I: Iterator>(mut items: I) -> Box<dyn std::any::Any>
where
    I::Item: 'static,
{
    Box::new(items.next().unwrap())
}

/// Calls `Into` of the parameter.
pub fn convert<T: Into<String>>(value: T) -> String {
    value.into()
}

/// Calls `Deref` of the parameter.
pub fn through<T: std::ops::Deref>(value: &T) -> usize {
    let _ = &**value;
    1
}

/// Calls a function pointer with an erased pointer: this crate cannot know the type behind it.
pub fn call(function: fn(*const ()), data: *const ()) {
    function(data);
}

/// Drops a value that a raw pointer holds.
pub fn drop_raw<T>(pointer: *mut T) {
    // SAFETY: the caller got the pointer from `Box::into_raw` and gives it up here.
    unsafe { drop(Box::from_raw(pointer)) }
}

/// A trait and its sub-trait: the upcast `dyn Sub` to `dyn Super` is done in this crate.
pub trait Super {
    /// Runs the impl.
    fn hit(&self);
}

/// The sub-trait.
pub trait Sub: Super {}

/// Upcasts the value inside this crate.
pub fn up(value: Box<dyn Sub>) -> Box<dyn Super> {
    value
}

/// A holder of a `dyn Super` that is made inside this crate from a `dyn Sub`: the upcast is here, and the
/// holder is an ADT of this crate.
pub struct Holder {
    inner: Box<dyn Super>,
}

impl Holder {
    /// Upcasts the value and keeps it.
    pub fn new(value: Box<dyn Sub>) -> Holder {
        Holder { inner: value }
    }

    /// Calls the kept value.
    pub fn run(&self) {
        self.inner.hit();
    }
}

/// A holder of a `dyn Debug` that this crate never builds: the caller coerces the value.
pub struct Slot {
    inner: Box<dyn std::fmt::Debug>,
}

impl Slot {
    /// Keeps the value.
    pub fn new(inner: Box<dyn std::fmt::Debug>) -> Slot {
        Slot { inner }
    }

    /// Shows the kept value.
    pub fn show(&self) -> String {
        format!("{:?}", self.inner)
    }
}

/// A holder of a future that the caller builds.
pub struct Task {
    inner: std::pin::Pin<Box<dyn std::future::Future<Output = ()>>>,
}

impl Task {
    /// Keeps the future.
    pub fn new(inner: std::pin::Pin<Box<dyn std::future::Future<Output = ()>>>) -> Task {
        Task { inner }
    }

    /// Runs the future one time.
    pub fn poll_once(&mut self) {
        let mut context = std::task::Context::from_waker(std::task::Waker::noop());
        let _ = self.inner.as_mut().poll(&mut context);
    }
}

/// A job is a future of this crate.
pub trait Job: std::future::Future<Output = ()> {}

impl<F: std::future::Future<Output = ()>> Job for F {}

/// Upcasts the job to a future inside this crate.
pub fn up_job(
    job: std::pin::Pin<Box<dyn Job>>,
) -> std::pin::Pin<Box<dyn std::future::Future<Output = ()>>> {
    job
}
