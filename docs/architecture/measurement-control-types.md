# Typed measurement controls

Part of #542. The existing measurements owner defines eligible scalar budget names, keyed name-budget kinds, measurement availability and metric-comparison outcomes. These are separate semantic domains; the later Delta SUPPORTED/UNKNOWN vocabulary remains independent.

Budget labels, JSON field names, arbitrary metric display labels and module/pair identities remain data. Profile capabilities and open Delta semantic-change strings remain unchanged. Native contracts pin the real fields and return status independently; valid legacy strings normalize only at the existing DTO and codec boundaries. Mixed governance codec versions remain pending under #542, not permanently exempted.

The source-backed native fixture also protects the three actual migrated governance codec tag helpers. Its codec projection is deliberately bounded; only the complete measurements owner has a whole-module root guard. Existing version readers remain pending under #542.

Production changes add70 net lines in11 existing source files (+132/-62), principally the four definitions and legacy input conversion. They remove the six-branch budget-tag decoder, label-driven budget dispatch and duplicated parser resolution reads. No production module, decoder framework, capability value or budget allowance is added. The14 authored Target entries describe types and ports independently of observed JSON;52 native controls include actual field/return/enum and decision mutations.
