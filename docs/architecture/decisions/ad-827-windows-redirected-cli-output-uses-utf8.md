# AD-827: Windows redirected CLI output uses UTF-8

## Decision

On Windows, write redirected CLI output as UTF-8 by default.
Keep the console encoding and an explicit `PYTHONIOENCODING` setting.

## Reason

The system code page cannot represent every project path.
A program that reads the output needs a predictable encoding.

## Alternative

Use the system code page for redirected output. This loses Unicode paths.

## Check

The installed-wheel test checks redirected text on Windows.
