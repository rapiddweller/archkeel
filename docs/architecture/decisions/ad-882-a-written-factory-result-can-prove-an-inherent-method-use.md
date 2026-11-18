# AD-882: A written factory result can prove an inherent method use

Status: proposed. Part of #880. Extends AD-604, AD-608 and AD-804.

## Context

The calls `factory::make().touch()` on a listed and an unlisted type yield the same pair gap.
The interface rule needs the type and the publication route, not just the module of the method.
Rust can choose a by-value trait method before a shared inherent method.

## Decision

- Follow the qualified function path to one free function with a complete item route.
  Read its written result type in the scope of the declaration.
- For a zero-argument call on that result, prove the one visible, exact inherent `&self` member.
  The caller must be at the crate root, with no import, explicit trait source, or unread expansion.
  Exclude by-value methods of the stable Rust 1.97 preludes at this earlier lookup step.
- Emit the existing method import with its type and AD-608 publication route.
  Resolve only this call. The new edge can establish reachability, not discharge another site's gap.

No field or wire format changes. The interface rule, contract and pins do not change.
A trait import, a competing prelude method, an opaque result or an unread publication stays open.
An incomplete type publication route can still pass with a witnessed public hop, not with a guess.

## Alternatives

Do not infer the type from the method name or from a known module pair.
Do not cancel a pair because another call uses the target through a listed type.
The remaining native gaps need their own evidence.

## Checks

`test_cli_native_rust_interface.py` runs both factory variants with rustc and checks the rule.
It checks a renamed root publication, an opaque result, a trait that wins, and a second unresolved
call on the same pair. The native self-check measures the effect on the real report.
