# translationCore AI Bridge v0.7.5 — Logos Navigation + Responsive UX

## Stability Fix — 2026-08-18

Windows field testing confirmed true three-application verse synchronization between **translationCore AI Bridge, Paratext and Logos Desktop**. This stability patch freezes that working connector design and hardens failure/recovery cases before further feature development.

- External navigation is now transactional at the broker level: a Logos/Paratext candidate is committed only after the Bridge actually accepts/loads it; rejected navigation rolls the broker back to the real Bridge reference.
- Rejected external references no longer nag on every poll. The same still-visible reference becomes retryable when relevant Bridge context changes (for example dirty work is saved/discarded, the selected project changes, or the loaded project set changes).
- External destination data is read/validated before the UI switches projects, reducing half-switched states if a verse is malformed.
- Logos helper reader/stderr threads are generation-isolated so a dead helper from generation N cannot inject a stale `helper stopped` result into generation N+1 after restart/timeout recovery.
- First Logos helper startup allows up to 10 seconds for cold TypeLib import/antivirus scanning; steady-state state requests remain 3.5 seconds and navigation requests 5 seconds.
- Added a per-Windows-session named mutex (`Local\translationCoreAIBridge.NavigationOwner`) so two Bridge processes cannot fight over Paratext/Logos navigation. A second Bridge can still review normally but cannot enable external sync until the owner releases it.
- Added versification safety messaging. Paratext continues to resolve references with its active project versification; cross-application synchronization is explicitly reference-label based. A detectable immediate Paratext reference mismatch fails closed and disables that sync direction.
- The v0.7.5 Tk UI tests are now included in the isolated-per-process Windows certification group, preserving the existing Tcl/Tk teardown safety policy.
- No Scripture-write capability was added, and the working Paratext Project Notes/navigation connector protocol remains unchanged.


## Field Logos fix 1 + collapsible fieldset legends (2026-08-17)

Windows diagnostics showed that Logos itself was registered correctly (`LogosCom.exe` present, TypeLib registry entry present, direct `LoadTypeLibEx` returned `S_OK`), but the original PowerShell late-bound COM path failed when `GetOpenPanels()` returned Logos-specific interfaces. This patch:

- replaces PowerShell late-bound calls on Logos-specific COM objects with an in-process C# raw-`IDispatch` shim;
- keeps the same local-only stdin/stdout helper architecture and the existing NavigationBroker;
- distinguishes **Logos detected** from **Navigation ready** and verifies API version, Bible data type and panel access before allowing sync;
- preserves no-network/no-credential/no-Scripture-write boundaries;
- changes Production and Settings & Log collapsible headers from full-width centred buttons to compact **left-aligned fieldset legends** with a disclosure arrow and horizontal rule;
- keeps collapsed sections genuinely compact and persistent across restarts.

Portable/full virtual-display test result after this patch: **175 discovered / 118 passed / 57 environment-dependent skipped / 0 failed**. Real Logos COM execution still requires Windows field testing because Logos is not available in the build environment.

## Release scope

v0.7.5 is a focused integration/UI release built from the working v0.7.4-paratext-buildfix4 baseline. It preserves the deterministic alignment compiler, strict validators, existing-work locks, Paratext note sync, project binding, transaction safety and no-automatic-Scripture-write boundary.

### Logos live verse navigation

- Added a Windows-local Logos COM connector using `LogosBibleSoftware.Launcher`.
- Reads Bible references from active/open Logos panels and navigates Logos with a Bible data-type navigation request.
- Added a central `NavigationBroker` for Bridge, Paratext and Logos.
- Navigation can originate from any of the three applications; accepted changes are forwarded to the other enabled connectors.
- Recent outbound references and unchanged polls are suppressed to prevent echo loops.
- A short connector-settling guard ignores a previously observed verse that can briefly reappear while an outbound navigation is still taking effect; once the requested verse is confirmed, a new user change is accepted immediately.
- Rapid Bridge/Paratext → Logos navigation is coalesced so the latest requested verse wins instead of replaying a stale queue.
- Logos COM calls used by continuous polling/navigation run off Tk's UI thread so a slow COM response does not freeze the reviewer interface.
- Logos synchronization starts disabled on every Bridge launch; enabling it is an explicit reviewer action.
- No Logos credentials, network listener or Scripture-writing operation were added.

### Dashboard and small-screen UX

- Selected exception details moved to a right-hand pane beside the exception queue, with a draggable divider and vertical scrolling.
- Removed the duplicate Workspace sidebar to reclaim horizontal space.
- Moved User Guide and Keyboard Shortcuts under a compact Help menu.
- Global tooltip placement now measures the tooltip and clamps/flips it inside the current monitor's usable work area, including Windows taskbar bounds.
- Normal action buttons receive tooltips even when an individual screen did not explicitly define one.

### Workflow naming and Alignment cleanup

- Renamed **AI Final Review** to **tN tW Review** and moved it before Alignment.
- Alignment toolbar is now workflow-oriented:
  - `Connect | Unalign Target | Undo | Redo`
  - `Fill Alignment Gaps | Audit Existing Alignment | Apply AI Proposal`
  - `Save Alignment | Approve Verse`
  - `More…` for diagnostics, large group view and backup restoration.
- On narrow screens the logical groups stack as groups instead of clipping individual actions.

### Production and Settings

- Every Production section is collapsible; the page remains vertically scrollable and stacks to one column on small screens.
- Every Settings & Log section is collapsible and the whole settings page is vertically scrollable.
- Added local lifetime API usage totals: total tokens and accumulated estimated cost recorded by this Bridge settings profile.
- Totals contain no API credential and are explicitly labelled as estimates/Bridge-local observations, not OpenAI account billing totals.
- Added compact Logos status/configuration sections without adding another full workspace tab.

### Packaging

- Application version is `0.7.5` across `VERSION`, Python runtime metadata, Windows EXE build naming and Inno Setup metadata.
- `logos_connector/logos_bridge.ps1` is included in PyInstaller `--add-data` so packaged Windows builds can locate the COM helper.
- The Paratext companion component remains protocol/plugin version `0.7.4`; no Paratext reinstall is required merely for the v0.7.5 UI/Logos changes.

### Test result in this build environment

```text
Discovered: 175
Passed:     118
Skipped:     57  (real translationCore/Windows backend not present)
Failed:       0
```

Additional v0.7.5 coverage includes book/reference mapping, echo/duplicate suppression, cross-connector source guards, package inclusion, local usage persistence, Workspace removal, tab ordering, dashboard split layout, Alignment workflow layout, tooltip coverage/clamping, collapsible sections and small-screen layout.

**Not claimed here:** real Logos Windows COM certification, real Paratext 9.5.110.1 runtime certification, Windows EXE/installer execution, or testing against the user's evolving live translationCore project data. Those remain Windows field-certification steps.

---

# translationCore AI Bridge v0.7.4 — Paratext Live Connector

## Field buildfix4 — Production UI responsiveness and Paratext cleanup

Windows field testing on a smaller display showed that the Production page could become taller than the available viewport after a translationCore project and Paratext were loaded. Long connector/project-note text also forced controls below the visible area.

- Production content is now vertically scrollable; no Paratext checkbox or action depends on screen height.
- Production automatically stacks its two columns on smaller windows and returns to two columns on wider displays.
- Production and Paratext action toolbars reflow into multiple rows instead of clipping off the right edge.
- **Security Scan** and **Performance Benchmark** are retained under one compact **Diagnostics…** menu instead of occupying separate toolbar buttons.
- The two separate Paratext cards were consolidated into one compact **Paratext · Live Connector + Project Notes** card.
- Long internal companion-file paths are no longer shown in the normal Production status line.
- Daily Paratext controls are reduced to **Connect / Refresh**, **Verify / Bind Project**, **Sync Notes**, and **Export Notes XML…**.
- Duplicate top-level Paratext export/sync buttons, the separate **Bind Active Project** button, the one-time installer button, and the diagnostic **Create Live Note** button were removed from Production.
- Connector installation/update is now kept in **Settings & Log**, where the one-time setup action belongs.
- **Verify / Bind Project** can explicitly bind an unbound project or replace a mismatched binding after confirmation, so a separate binding button is no longer required.
- The long live-review checkbox label was shortened to **Auto-send review notes**; its tooltip retains the full Needs Discussion / Reject AI behavior.

v0.7.4 keeps the v0.7.3 Alignment Reliability engine and adds the first complete **Paratext local Plugin API connector source/build/install workflow**, targeted for field certification with **Paratext 9.5.110.1 on Windows**.

## Field buildfix3 — Project Notes author/sync repair

After Windows field testing showed that verse synchronization works but **Sync Notes to Paratext** fails with Registry HTTP 403 `unauthorized_client`, the primary Project Notes workflow was corrected:

- **Verify Paratext Project** now verifies the active project through the working local Plugin API connector instead of Registry/Data Access authentication.
- **Sync Notes to Paratext / Sync to Paratext / Sync Current Notes** now batch-create Project Notes through the local named-pipe connector and `IProject.AddNote`.
- Paratext itself remains responsible for the real note author; the connector requires and reports the current logged-in Paratext user.
- `Notes_AI_Suggestion.xml` remains only the Bridge companion/export filename. It is never treated as a Paratext member account.
- AI provenance remains separate as `AI Suggestion` (`extUser` for Notes 1.1 export; `[AI Suggestion]` prefix for live Plugin API notes).
- API-ready exports normalize `comment@user` to the real detected/configured Paratext user.
- successful live batch syncs are fingerprinted in `live_sync_state.json` to prevent accidental duplicate creation on repeat clicks; changed-after-sync notes are held for attention instead of duplicated automatically.
- local note failures now identify AUTHOR / WRITE_LOCK / ADD_NOTE stages more clearly.

The legacy Data Access client remains in the source for advanced/future compatibility, but the normal UI no longer depends on its Registry grant.

## Paratext Live Connector

The release adds a Paratext startup plugin implementation (`IParatextStartupAutomaticPlugin`) that communicates with the Bridge through the local Windows named pipe:

```text
\\.\pipe\translationCoreAIBridge
```

The connector exposes only three actions:

1. `get_state` — current Paratext user, project/project ID/language, reference, sync group, exact Scripture selection and nearby context.
2. `set_reference` — two-way Scripture navigation through the active Paratext scroll/sync group.
3. `create_note` — direct Paratext Project Note creation on the exact Scripture selection or verse.

There is **no Scripture-write action** and the plugin does not call `PutUSFM`, `PutUSFMTokens`, or `PutUSX`.

## Build/install on the user's Paratext computer

The release intentionally includes the C# plugin source plus a one-click Windows builder/installer instead of pretending a precompiled `.ptxplg` has been certified here. The builder locates the installed Paratext, references that installation's PluginInterfaces assembly, invokes the Windows .NET Framework C# compiler, creates `translationCoreAIBridge.ptxplg`, and installs it under the Paratext `plugins` folder.

Root commands:

```bat
diagnose_paratext_connector.bat
build_paratext_connector.bat
install_paratext_connector.bat
uninstall_paratext_connector.bat
```

Paratext must be closed during install/update/uninstall.

## Explicit project binding

A live Paratext connection is not enough to authorize notes. Each translationCore project must be explicitly bound to the active Paratext project ID with **Verify / Bind Project**.

If the active Paratext project later changes, the Bridge displays `PROJECT MISMATCH` and blocks live notes/navigation until the correct project is reopened or the binding is explicitly changed. This prevents reviewer notes from being written into the wrong Paratext project when two projects happen to be on the same verse.

## Two-way verse navigation

After binding and placing the Paratext Scripture window in scroll/sync group A–E, **Sync verse navigation** can be enabled.

- Bridge verse changes are sent to Paratext.
- Paratext reference-change events are polled through the connector and move the matching bound translationCore project.
- origin IDs prevent ordinary Bridge-originated navigation from being echoed back indefinitely.
- the connector does not silently choose a Paratext scroll group.

## Direct selected-text Project Notes

**Sync Notes** uses the active Paratext Scripture selection when possible. If the Bridge supplies selected text instead, the connector asks Paratext for matching Scripture selections.

- one exact/unique match → note is created;
- duplicate text with one context match → that occurrence is used;
- unresolved multiple occurrences → the operation is blocked and the reviewer is asked to select the exact occurrence in Paratext;
- no selected text → a verse-level note anchor is used.

Project Notes are created with a `ProjectNotes` write lock. The actual note author remains the current Paratext user; AI-originated content is visibly prefixed `[AI Suggestion]` rather than impersonating a Paratext member.

## Optional live reviewer-note forwarding

When enabled, **Needs Discussion** and **Reject AI** reviewer comments can additionally be sent as live Paratext Project Notes after the Bridge's own local audit record is successfully saved. A live-note failure never erases the local reviewer decision.

## Existing Paratext workflows retained

Notes 1.1 XML export remains available. After field buildfix3, the normal Verify/Sync UI uses the local Plugin API connector; the Data Access client is retained only as an advanced/legacy code path.

## Alignment reliability retained

All v0.7.3/v0.7.3.1 alignment protections remain:

- AI links → deterministic compiler → strict validator → human approval;
- Fill Alignment Gaps;
- Audit Existing Alignment;
- hard locks/protected legacy work;
- stale request fingerprints;
- no mass rewrite of completed projects.

## Test discovery

v0.7.4 discovers:

```text
Core/data/production: 118
Isolated real-Tk GUI:  34
Total:                152
```

The v0.7.4-specific portable/static connector tests pass in the build environment. The GUI connector tests pass under isolated virtual display. The actual `.ptxplg` compilation, loading in Paratext 9.5.110.1, Windows named-pipe behavior, and direct Project Note behavior require the user's Windows/Paratext field certification and are not claimed as completed in this build environment.
