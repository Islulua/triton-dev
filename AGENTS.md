# Repository rules for people and coding agents

- Read README.md, STATUS.md and the touched module's TODO.md before changes.
- Keep CLI parsing separate from service logic. Use the common process runner; never execute model-produced shell.
- Do not modify real SDKs, /login_home, user shell profiles, source branches or credentials in tests.
- Production defaults stay in env/settings.py; tests inject temporary paths and clients.
- Unknown native mapping, ABI, commit provenance or build recipes must return an explicit error/TODO, not fabricated success.
- env must not implicitly rebuild repositories. build must not activate environments or reset source.
- run reports raw failure; diagnosis applies the explicit failure predicate. Preserve first failure and evidence scope.
- Add tests beside each module; update its TODO.md and STATUS.md in the same change.
- Test real subprocess boundaries, shell quoting and state restoration when relevant. Do not mock away the behavior being asserted.
- No live AI, private network, devices or third-party messaging during default tests.
- Public interface changes update describe/help, examples and tests together.
- Before commit: run pytest, ruff, package build and installed-wheel smoke checks. Report unavailable integrations honestly.
- No hardcoded credentials, internal log dumps or downloaded binaries in git. Keep SDK and build artifacts outside the repository.
