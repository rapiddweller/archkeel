# AD-558: An import counts as a use when every boundary up to the root publishes it

## Status

Accepted. Part of #880. It amends AD-514.

## Decision

AD-514 counted an import from outside a mount only for a mount of the root.
A deeper mount counted its local imports and nothing else.
The core now walks the owners of the mount up to the root, as release 4.0.1 does
(`_import_published_through_ancestors`).

For an import from outside the domain of the mount, the walk starts at that mount:

1. At each step, the owner contract must own the target in the component that holds the mount.
2. The `public` entries of that component must cover the imported name.
3. If the domain of an owner holds the source, the walk ends there. Both modules need an owner in its contract.
4. At the root, the source needs an owner in the root contract.
5. An owner that is not in the tree publishes nothing.

An entry that the walk reaches is used, as for a mount of the root.
The rule is language-free. It reads components, domains and the imports of the model.
A boundary that does not publish the import keeps `interface.usage_unknown`.

## Reason

On DATAMIMIC CE, 168 of 316 `interface.usage_unknown` rows were entries of a mount at depth two or three.
Their importers lie outside the mount and cross each boundary through a published entry.
Release 4.0.1 counted them as used. The core only had the proof for one boundary.

## Checks and limits

`tests/test_cli_python_deep_mounts.py` builds a tree of three levels.
The import crosses three boundaries. One variant publishes at each boundary and gives PASS.
Two variants stop the publication at the root and at the middle component.
Release 4.0.1 gives `interface.unused` at the same pointers. The core gives `interface.usage_unknown`.
The core never clears an entry that 4.0.1 refuses.
The use of an entry by a declared facade signature is not part of this decision.
