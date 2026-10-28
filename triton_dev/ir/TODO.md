# Kernel / IR

- [x] Pinned BSD TritonParse location parser with attribution; no compiler source changes.
- [x] Bounded embedded JSON/NDJSON/gzip import; major dynamic stages; exact file/range and inline source mapping.
- [x] Existing web navigation, locally bundled Monaco editors, multiple stage panes, fixed revisions, same-stage diff and linked detached windows.
- [x] Explicit illustrative sample; edited source invalidates mappings; stale responses cannot replace current results.
- [x] Validated compile spec, registered external isolation launcher, actual ASTSource/compile worker, asm extraction and diagnostics.
- [x] SQL workspace tasks, idempotency, queue leases, cancellation, persisted compilation history and API/CLI.
- [ ] Validate actual TX82 SDK/toolchain and compiler location preservation on the internal Linux server.
- [ ] Automatic capture from arbitrary registered pytest projects, SDK environment builder integration, stop-at-stage compilation and pass-level tracing.
- [ ] Cross-SDK compiler build identity probes and reusable compilation-result cache (current worker uses an isolated per-task Triton cache).

The external launcher is administrator-owned and MUST provide filesystem/network/resource isolation and process cleanup. No edited Python runs in the API process. An empty compiler registry disables compilation. Import locations never cause reads from compiler-supplied file paths. See docs/KERNEL_IR.md.
