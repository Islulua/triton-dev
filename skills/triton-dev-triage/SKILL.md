---
name: triton-dev-triage
description: Diagnose Triton test failures with recorded pytest stages, explicit failure predicates and bounded SDK comparisons using triton-dev; export evidence without inventing component blame.
---

Discover installed commands with `capabilities` and `describe`. Read a run with `runs show ID`; preserve the original record and create new records for experiments.

- Record pytest targets with `runs start --pytest --cwd PROJECT -- TARGETS`. This path accepts test targets only; use project pytest configuration for options. `runs rerun ID --failed` reuses the original working directory, interpreter and environment but selects recorded failed nodeids. Re-execution uses current source, not a historical source checkout.
- Define the target failure before searching. `diagnose classify ID --predicate FILE` supports text, nonzero exit, pytest stage and finite flat numerical-array predicates. Malformed or nonfinite numeric observations are insufficient evidence.
- `diagnose history --versions OLDEST ... NEWEST --predicate FILE --repeat N --budget N -- COMMAND` exhaustively checks the explicit ordered SDK list within budget. A first failing artifact is not a commit culprit. Unavailable versions, inconsistent repetitions and exhausted budgets must remain visible.
- Do not infer a component defect from a stage name or a traceback alone. SDK association, component attribution and repository/commit attribution are different evidence scopes.
- Export terminal runs using `runs export ID --output FILE.zip`; verify with `runs verify-export FILE.zip`. Specify `--redact-env VARIABLE` for known secret literals. Redaction is heuristic; export contains records/logs/events, not tensor inputs or SDK binaries.

For offline controller evaluation, `agent workflow CONFIG --checkpoint FILE` accepts trusted registered recipes and scripted model messages. The model selects recipe IDs, never argv. Two good and two bad observations are required for `change_associated`; that conclusion concerns registered experiments, not a particular team. Resume preserves budgets and never automatically repeats a pending side effect. Live model quality and device behavior require separate validation.
