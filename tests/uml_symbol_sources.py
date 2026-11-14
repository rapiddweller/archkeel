# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The TypeScript sources of the symbol plants (AD-512)."""

from __future__ import annotations

SOURCE = """import { t } from '../b/t';
export const used = t;
export interface Port { run(value: number): string; }
export class Unit {}
export class Client implements Port {
  private token: string = '';
  run(value: number): string { return helper(value); }
}
export enum State { READY = 'ready', STOPPED = 'stopped' }
export function helper(value: number): string { return String(value); }
export function build(): Unit {
  const item = new Unit();
  return item;
}
export type Text = string;
export const VERSION = 1;
"""

LOCAL_FUNCTION = """export function go(): number {
  function helper(value: number): string { return ''; }
  return helper(1).length;
}
"""
LOCAL_METHOD = """export class Holder {
  hold(): number {
    function helper(value: number): string { return ''; }
    return helper(1).length;
  }
}
"""
CATCH = """export function guard(): void {
  try { } catch (helper: any) { helper(1); }
}
"""
LOCAL_CLASS = """export function make(): void {
  class Unit {}
  const made = new Unit();
}
"""
TYPE_PARAMETER = "export function gen<Unit>(x: Unit): Unit { return x; }\n"
LOCAL_INTERFACE = """export function usePort(): void {
  interface Port {}
  const p: Port | undefined = undefined;
}
"""
LOCAL_BASE = """export function derive(): void {
  class Unit {}
  class Derived extends Unit {}
}
"""
ARROW = """export function arrow(): number {
  const helper = (value: number): string => '';
  return helper(1).length;
}
"""
PARAMETER = "export function take(helper: any): number { return helper(1); }\n"
REBOUND = """export function swap(): void {
  let swapped = new Unit();
  swapped = new Client();
}
"""
LOOSE = """export function loose(): void {
  let held: any = new Unit();
}
"""


MIXIN = """function Mix(base: any): any { return base; }
export interface I9 {}\nexport class Mx extends Mix(Unit) implements I9 {}
"""
CTOR = "export class PP { constructor(z: number) {} }\n"
HASH = "export class Pv { #x = 1; }\n"
DECORATED = """function mk(target: any): void {}
@mk
export class Dec {}
"""
MERGED = """export class Nm {}
export namespace Nm { export function f(): void {} }
"""
AMBIENT = "declare module 'ext' { export class Amb { z: number } }\n"
NAMESPACE = "export namespace Ns { export const k = 1; }\n"
OTHER = {
    "src/b/t.ts": "export function tfn(): void {}\nexport { real as shown } from './u';\n",
    "src/b/u.ts": "export function real(): void {}\n",
}


TARGET = "app.src.b.t_x2e_ts"
DYNAMIC = """export async function dyn(): Promise<void> {
  const loaded = await import('../b/t');
  loaded.tfn();
}
"""
NAMESPACE_IMPORT = """import * as ns from '../b/t';
export function viaNs(): void { ns.tfn(); }
"""
TYPE_IMPORT = """import type { Alias } from '../b/t';
export function useType(x: Alias): void {}
"""
RENAMED = """import { shown } from '../b/t';
export function viaShown(): void { shown(); }
"""
REQUIRED = """const t = require('../b/t');
export function viaRequire(): void { t.tfn(); }
"""
DROPPING = '{"compilerOptions": {"strict": true}, "exclude": ["src/a/hidden.ts"]}\n'
HIDDEN = """import { helper } from './one';
export function hid(): void { helper(1); }
"""
