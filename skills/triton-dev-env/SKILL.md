---
name: triton-dev-env
description: Query, freeze, compare and use SDK/wheel combinations through an installed triton-dev CLI when managing Triton development environments.
---

Use `triton-dev capabilities --json` and `triton-dev describe <command-id> --json` to discover the installed interface before selecting commands. This skill uses the installed Python CLI; no model API key is needed.

- Query real candidates with `env sdk list` / `env sdk inspect`. Resolve “latest” or a date to a concrete SDK before explaining a choice.
- Use `env preflight` / `env plan` to check interpreter tags and selected wheel dependencies. `constraints=unknown` means unresolved dependencies, not compatibility approval.
- Save a reproducible selection with `env save NAME --sdk SDK [--triton-sdk SDK] [--torch-sdk SDK] [--raops-sdk SDK]`. Names are immutable. `env saved show/diff/list` inspect them. Saving references and hashes does not archive binaries.
- Use `env prepare --saved NAME --non-interactive` to prepare, then `env verify --saved NAME` and `env exec --saved NAME -- COMMAND`. Preparation does not activate the calling terminal.
- If source hashes change, stop restoring that selection and report SOURCE_CHANGED; do not silently substitute another SDK or bypass checking.
- Native cmodel/LLVM mixing and actual build recipes are unsupported until their mappings are confirmed. Never emulate a component switch by guessing library search order.
- Report installation, Python import, native-loading and functional verification separately. Mock SDKs are explicitly labeled and do not demonstrate real Triton compatibility.
- Use `--sdk-root` and `--cache-root` only when requested or needed for an isolated mock/demo. Do not install over the tool interpreter or modify shell profiles.

For persistent execution, `runs start --saved NAME -- COMMAND` records evidence. Read errors and raw child return codes even if the outer envelope says `status=ok`.
