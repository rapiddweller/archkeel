# Source name visibility implementation

Approved bounded #542 slice, based on bb3e498b9c43afc954ef9fe7078595983e0b3c2f.

1. Add actual producer/consumer behavior tests and confirm RED against the frozen base.
2. Add one two-value Facts owner and precise optional reader; migrate the two Python writers, common import-origin writer and Dart's equivalent import field. Replace the three closed controls without changing language API visibility.
3. Author the Facts API intent and precise complete-function guards; prove native owner/input/return/control weakening with unchanged contracts.
4. Run affected regressions, hygiene, lint/typecheck, actual native-site and isolated producer/report parity checks. Hand the frozen source to the final #542 union review.

No issue/PR, DTO, module, generic control framework, baseline write or limit increase is needed.
