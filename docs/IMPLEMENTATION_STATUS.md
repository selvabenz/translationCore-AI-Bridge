# Implementation Status — v0.7.5

## v0.7.5 implemented

- [x] Windows-local Logos COM helper and Python connector client.
- [x] Bridge/Paratext/Logos NavigationBroker with echo/duplicate suppression.
- [x] Latest-wins asynchronous Logos outbound navigation.
- [x] Dashboard side-by-side exception details.
- [x] Workspace sidebar removal and Help/User Guide relocation.
- [x] Global screen-aware tooltip clamping and action-button tooltip coverage.
- [x] Production/Settings collapsible sections and small-screen scrolling.
- [x] tN tW Review rename/reorder.
- [x] Alignment workflow toolbar cleanup.
- [x] Bridge-local lifetime token/estimated-cost totals.
- [ ] Real Windows Logos COM field certification.


## Implemented

### Alignment reliability

- [x] AI individual-link schema.
- [x] Deterministic Alignment Compiler.
- [x] 1→1 / 1→many / many→1 / many→many compilation.
- [x] Strong/uncertain/low-confidence edge policy.
- [x] Duplicate-link deduplication.
- [x] Weak-bridge overmerge prevention.
- [x] Discontinuous token relationship support.
- [x] Explicit implicit-source handling.
- [x] Explicit target-only grammatical/natural-expression candidate handling.
- [x] Final strict translationCore proposal validation retained.
- [x] Fill Alignment Gaps workflow.
- [x] Read-only Audit Existing Alignment.
- [x] Compiler diagnostics viewer/audit record.

### Existing-work protection

- [x] HARD_LOCK for explicit human-approved alignment.
- [x] PROTECTED_LEGACY for completed historical alignment.
- [x] PARTIAL_PROTECTED for useful partial work.
- [x] OPEN for untouched work.
- [x] Read-only Existing Work Compatibility Scan.
- [x] Hash-only pre-v0.7.4 migration/provenance snapshot.
- [x] No automatic mass realignment.
- [x] Protected-group bridge conflict blocking.
- [x] Hard-lock extension blocking.

### Async/state safety

- [x] Request ID.
- [x] Project/reference binding.
- [x] Source-token fingerprint.
- [x] Target verse/token fingerprint.
- [x] Alignment fingerprint.
- [x] Stale result discard after navigation/edit/project state change.
- [x] Clear prior pending proposal before a new alignment request.

### Identity / integration foundation

- [x] Read-only Door43 project Git identity detection.
- [x] Distinct labelling from live translationCore authentication.
- [x] Paratext local Windows named-pipe client foundation.
- [x] C# named-pipe server/protocol skeleton for future plugin adapter.
- [x] Local connector probe/status UI.
- [x] Optional Bridge-side verse-navigation sync hooks.
- [x] Existing Paratext Notes 1.1 Data Access path retained.
- [x] No local connector Scripture-write command.

### Existing production capabilities retained

- [x] Manual many-to-many alignment, Undo/Redo and safe save.
- [x] Word Alignment completion/invalidation lifecycle.
- [x] TN/TW evidence/preselection + human approval + native checkData sync.
- [x] AI full verse review and false-positive policy.
- [x] Human QA decisions and Scripture correction with stale propagation.
- [x] Translation Helps knowledge graph/provenance.
- [x] Terminology Decision Center and analytics.
- [x] Psalms candidate QA.
- [x] Crash recovery, Git checkpoints, reports, roles/assignments, metrics/security.
- [x] Responsive UI, text wrapping/scrolling fixes, tooltips and reviewer shortcuts.
- [x] Language/plugin detection and multilingual confidence-coloured proposal display.
- [x] Paratext Notes 1.1 export/verification/explicit Data Access sync.

## Deliberately not claimed in v0.7.4

- [ ] A compiled/installed Paratext `.ptxplg` companion.
- [ ] Complete live Paratext Plugin API adapter.
- [ ] Automatic Paratext Scripture editing.
- [ ] Automatic rewriting of completed historical alignments.
- [ ] Proof that project Git username equals the currently logged-in translationCore account.
- [ ] Windows EXE/installer certification without running the Windows checklist on the generated binary.

## Upgrade effect on worked projects

No redo is required by the upgrade itself. Existing finished alignment remains project authority. AI can audit it but cannot silently replace it. Partially worked verses preserve their established groups and use gap filling for unresolved material.

## v0.7.4 live Paratext integration

Implemented in source/package:

- Paratext 9.5 automatic startup-plugin adapter;
- local named-pipe transport;
- current user/project/reference/selection state;
- two-way verse-navigation protocol and echo guard;
- explicit per-project binding/mismatch protection;
- selected-text/verse-level direct Project Note creation;
- Project Notes write-lock handling;
- exact/repeated-text anchor safeguards;
- Windows diagnose/build/install/uninstall scripts;
- PyInstaller/Inno packaging of connector tooling;
- no Scripture-write protocol/action.

Still requires Windows field certification:

- compilation against the actual Paratext 9.5.110.1 PluginInterfaces assembly;
- plugin loading by that installed Paratext;
- real named-pipe handshake;
- real navigation event behavior;
- real selected-text Project Note marker placement and project permissions.
