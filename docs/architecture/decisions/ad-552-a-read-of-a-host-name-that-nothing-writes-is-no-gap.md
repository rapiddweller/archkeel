# AD-552: A read of a host name that nothing writes is no gap

Status: accepted. Part of #880. It amends AD-460 and AD-540.

## Context
graphql-js has 6 gaps on main. Four are `process` in `jsutils/instanceOf.ts:5,7`:
`globalThis.process && process.env.NODE_ENV === 'production'`. No `@types/node` declares `process`,
so the use of a free name that is no standard global gave "Script global process has no unique
unconditional publication". 4.0.1 read no free name.

## Decision
A use of a free name is a dependency on the host, as a standard global is (`Target::Builtin`), when
all of this holds. The collector proves it for each use.
1. The use is contained (AD-540): the head of a chain of literal members that is the operand of
   `typeof`, `!` or a comparison, the left side of `&&`, or a condition. The use builds no code and
   keeps no reference.
2. Nothing in the project publishes, writes, binds or vendors the name, and the project has no
   write with an unknown name (`global_stable`).
3. The name is no root (`window`, `self`, `globalThis`, `top`, `parent`, `frames`), no host name of
   a loader (`exports`, `module`, `define`, `global`).

A use that is called (`process.nextTick(f)`), passed, stored, returned, keyed (`process.env[name]`)
or the left side of `||` and `??` keeps its gap. So does a name that a file writes (`o.process = 1`,
`globalThis.process = x`) or publishes (`window.process = {}`).

Why sound. With condition 2 no scanned file can make the name a module of the scan, so the read is
no edge between two modules. With condition 1 the read gives a string or a Boolean or a falsy
value, so it cannot reach `Function` or the global object. The edge to the host is recorded, not
dropped.

## What does not change
- `execution/execute.ts:1304` `source[info.fieldName](...)` is a CALL with a key from the caller:
  AD-508 rule 2 and the owner decision keep it a gap.
- `jsutils/suggestionList.ts:129` `rows[aLength % 3][bLength]` is a computed READ, but its value is
  returned (`return distance <= threshold ? distance : undefined`). With `rows[n]` a function and
  `bLength` the text `constructor` the value is `Function`, and `Function <= 'z'` is true, so the
  value leaves. It stays a gap until a proof that `.length` is a number exists.

## Price
graphql-js 6 gaps become 2. hono and zod keep their gaps (host entry, syntax errors).

## Mutation table
Removing the containment test turns `a_use_that_calls_stores_or_passes_a_host_name_keeps_its_gap`.
Removing the write or publication test turns `a_host_name_that_a_file_writes_keeps_its_gap_for_a_read`.
