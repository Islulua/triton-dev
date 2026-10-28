# Kernel / IR browser QA — 2026-10-27

Built production UI served by the actual multi-user backend on loopback with a dedicated temporary SQLite database. No real SDK or compiler registered on this macOS host.

- Existing native navigation and name session work; illustrative provenance stays visible.
- Imported examples/ir_demo.json through the actual browser file chooser and authenticated /api/ir/import route; separate history entry retained.
- Source line 9 highlights two lines in TTIR/LLVM IR; line 11 highlights addf/fadd. Editing source clears mappings immediately.
- Stage selectors, third pane addition/removal, same-stage diff and return to normal editor work.
- Independent browser window receives current document, selects TxIR, follows source line 11 and displays a linked highlight.
- 390×844: document width375, viewport390, no root horizontal overflow; editor panes scroll locally.
- 1440×1000 desktop: three-pane source/TTIR/LLVM IR view captured in desktop.png. mobile.png records narrow view.
- Found and fixed Monaco DiffEditor disposal order error by detaching models before release; final build switch into/out of diff and between stages produced no error from the new build.
- Actual Triton compile worker and private SQL task integration are covered by subprocess protocol tests. Actual TX82 compilation requires the registered isolated internal toolchain; no simulated compiler result is claimed.
