# Changelog

## v0.7.5 — Logos Navigation + Responsive UX

### Stability Fix — 2026-08-18
- Made external navigation commit/rollback safe and retryable after Bridge context changes.
- Isolated Logos helper generations to prevent stale reader-thread responses after helper restart.
- Added longer cold-start and navigation-specific Logos timeouts while keeping Tk non-blocking.
- Added single-owner Windows navigation mutex for multiple Bridge instances.
- Added reference-label/versification safety notice and fail-closed detectable Paratext mismatch handling.
- Moved all v0.7.5 real-Tk tests into isolated Windows certification processes.

### Certification fix 1 — 2026-08-17
- Corrected a stale v0.6 small-screen GUI certification assertion that still expected the old `AI Review` tab position and a `sidebar` widget removed intentionally in v0.7.5.
- Certification now checks the intended compact order `Dash`, `tN/tW`, `Align` and verifies that the Workspace sidebar is absent.
- Runtime application behavior is unchanged.


- Added local Windows Logos COM verse navigation and a Bridge/Paratext/Logos navigation broker with echo suppression.
- Added latest-wins asynchronous Logos navigation/polling so COM latency does not freeze Tk or replay stale verse queues.
- Moved Dashboard exception details beside the queue with vertical scrolling.
- Removed the Workspace sidebar; moved User Guide/shortcuts to Help.
- Renamed AI Final Review to tN tW Review and moved it before Alignment.
- Simplified Alignment actions into workflow groups with `|` separators and `More…` for secondary tools.
- Added screen-clamped tooltips and guaranteed tooltips for normal action buttons.
- Made Production and Settings sections collapsible/scrollable.
- Added Bridge-recorded lifetime token and estimated-cost totals.
- Preserved v0.7.4 Paratext note/navigation behavior and existing-work safety.

## v0.7.4 — Paratext Live Connector

### v0.7.4 field buildfix3
- moved Verify Project and all normal note-sync buttons from Registry/Data Access authentication to the already-working local Paratext Plugin API connector;
- real current Paratext user is used as Project Note author; `Notes_AI_Suggestion.xml` is treated only as an export filename;
- preserved AI provenance separately as `AI Suggestion`;
- normalized exported Notes 1.1 `comment@user` to a real Paratext user;
- added duplicate-safe live batch sync fingerprints and clearer Project Note failure stages.

- Added complete Paratext 9.5 startup-plugin source for live local integration.
- Targeted field certification for Paratext 9.5.110.1.
- Added one-click Windows diagnose/build/install/uninstall scripts for the `.ptxplg` connector.
- Builder compiles against the PluginInterfaces assembly from the installed Paratext.
- Added current user/project/project ID/language/reference/sync-group/selection state.
- Added two-way verse navigation with origin/echo protection.
- Added explicit per-translationCore-project Paratext project binding and mismatch blocking.
- Added direct Project Note creation through the Plugin API with exact-selection/ambiguity guards.
- Added optional live Needs Discussion / Reject reviewer-note forwarding.
- Kept actual Paratext user as note author and identifies AI-originated content in the note body.
- Connector write scope is Project Notes only; no Scripture-write protocol or `PutUSFM`/`PutUSX` call.
- PyInstaller now bundles the connector builder/source; Windows installer adds connector install/uninstall shortcuts.
- Retained Notes 1.1 XML/Data Access path and all v0.7.3 alignment reliability protections.
- Expanded discovery to 118 core/data + 34 isolated Tk GUI tests (152 total).

## v0.7.3 — Alignment Reliability & Integration Foundation

- Replaced direct AI final-group generation with individual linguistic links plus a deterministic Alignment Compiler.
- Added deterministic 1→1, 1→many, many→1 and many→many compilation.
- Added confidence thresholds so weak edges cannot over-merge components.
- Added duplicate-link deduplication and retained the strict final duplicate-token validator.
- Added explicit implicit-source and target-only grammatical/natural-expression handling.
- Added discontinuous relationship support without adjacency assumptions.
- Added `Fill Alignment Gaps` as the default alignment AI workflow.
- Added read-only `Audit Existing Alignment`.
- Added HARD_LOCK / PROTECTED_LEGACY / PARTIAL_PROTECTED / OPEN existing-work policy.
- Added read-only Existing Work Compatibility Scan.
- Added hash-only pre-v0.7.3 migration/provenance snapshot; no mass realignment.
- Added immutable AI request context with source/target/alignment fingerprints and stale-response discard.
- Clear pending alignment proposal before every new request.
- Added compiler diagnostics and protected-group conflict reporting.
- Added Door43 project Git identity detection without reading/copying credentials.
- Added Paratext local Plugin API connector foundation using Windows named-pipe transport; no Scripture write command and no compiled `.ptxplg` claim.
- Added v0.7.3 Alignment reliability UI controls/tooltips.
- Added recursive project `.gitignore` rules including `.venv-build` subfolders.
- Expanded certification to 106 core/data + 32 isolated Tk GUI tests (138 total).

## v0.7.2

- Fixed Dashboard long-summary overflow using a wrapped selected-summary panel.
- Added grapheme-safe Tamil/Indic Scripture editing behavior.
- Moved reviewer shortcuts to tooltips.
- Corrected Paratext Notes 1.1 project binding and explicit sync behavior.
- Added green AI activity pulse.

## v0.7.1

- Added compatibility with supplied Paratext CommentList exports and migration support.
- Added Dashboard/Result + Evidence wrap corrections.

## v0.7.0

- Added reviewer-speed controls, false-positive policy, language/plugin behavior, multilingual/confidence proposal coloring and Paratext note groundwork.
### v0.7.5 Logos Fix 4 (2026-08-18)
- Replaced the LogosApplication raw-IDispatch workaround with runtime import of the registered Logos Bible Software 4 Type Library via .NET `TypeLibConverter`.
- Logos application, panel, reference and navigation calls now use generated COM-imported interface metadata; this addresses real Windows diagnostics where `Launcher.Application` worked but `ApiVersion` returned `DISP_E_MEMBERNOTFOUND` through raw IDispatch.
- Added per-LogosCom.exe interop caching under LocalAppData and retained restart recovery, no-network/no-credentials behavior, and the existing navigation broker.

