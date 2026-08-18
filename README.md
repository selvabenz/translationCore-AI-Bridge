# translationCore AI Bridge v0.7.5 — Logos Navigation + Responsive UX

Windows desktop companion for translationCore Bible translation projects. The Bridge combines deterministic translationCore-compatible data handling with AI-assisted alignment, Translation Notes/Words review, QA, terminology and evidence gathering while keeping the reviewer as final authority.

## v0.7.5 focus

v0.7.5 builds on the stable v0.7.4 Paratext workflow and adds **local Logos Desktop verse navigation**, plus the small-screen/UI cleanup requested during field use.

```text
                       Navigation Broker
                             │
            ┌────────────────┼────────────────┐
            │                │                │
     AI Bridge UI       Paratext 9.5      Logos Desktop
            │                │                │
            └──── accepted Scripture reference ────┘
```

Navigation may originate in the Bridge, Paratext, or Logos. The Bridge is the broker: it suppresses recent echoes and duplicate polls, validates the reference against loaded translationCore projects, and forwards accepted changes only to the *other* enabled connector(s). Rapid Bridge→Logos requests are coalesced so the latest verse wins.

### Logos connector

- Windows-local COM automation through the registered `LogosBibleSoftware.Launcher` component;
- reads the current Bible reference from active/open Logos panels;
- Bridge → Logos verse navigation;
- Logos → Bridge verse navigation;
- Paratext → Bridge → Logos and Logos → Bridge → Paratext when both sync options are enabled;
- no Logos credentials, network listener, or Scripture-writing command;
- Logos synchronization starts **off** each Bridge session so another application cannot silently take navigation control after restart.

The Logos COM helper is packaged with the Windows build. Actual COM behavior must still be field-tested against the user's installed Logos Desktop version; this source environment cannot certify Windows COM.


### v0.7.5 Stability Fix

After Windows field testing confirmed Bridge ↔ Paratext ↔ Logos synchronization, the stability patch adds broker rollback/retry safety, Logos helper-generation isolation, cold-start timeout hardening, a single-owner Windows navigation mutex, and explicit versification/reference-label safety messaging. It does not add Scripture writing or change the working Paratext Project Notes protocol.

## v0.7.5 responsive/UI changes

- Dashboard exception queue and selected-exception summary are side-by-side in a draggable pane; the details pane has vertical scrolling.
- The duplicated **Workspace** sidebar is removed. **User Guide** and **Keyboard Shortcuts** live under **Help**.
- **AI Final Review** is renamed **tN tW Review** and appears before Alignment.
- Alignment actions are reduced to the reviewer flow: manual edit → AI preparation/audit → human save/approval, with secondary diagnostics/restoration under **More…**.
- Tooltips are guaranteed for normal action buttons and are clamped to the visible monitor work area so they do not run off-screen.
- Production and Settings & Log sections are collapsible and remain vertically scrollable on small screens.
- Settings shows Bridge-recorded lifetime API tokens and estimated API cost. These totals are local Bridge observations, **not an OpenAI account billing statement**.

## Paratext remains preserved

v0.7.5 does not replace the v0.7.4 Paratext companion connector. The existing local named-pipe/Plugin API workflow remains the primary route for project identity, two-way verse navigation and Project Notes. Existing translationCore↔Paratext project binding and no-Scripture-write safeguards remain in force.

## Main workspaces

- **Dashboard** — exception-first project review.
- **tN tW Review** — Translation Notes/Words evidence and human decisions.
- **Alignment** — manual alignment, gap-fill AI, read-only audit and human approval.
- **Quality Queue** — deterministic/AI issues and audited Scripture correction.
- **tC Check State** — native translationCore selections/comments/invalidation state.
- **Knowledge Base** — TN/TA/TW/TWL/source/reference evidence.
- **Terminology** — trusted terminology decisions and analytics.
- **Psalms QA** — candidate structure/parallelism QA.
- **Production** — recovery, Git, team roles, reports, Paratext, Logos and metrics.
- **Settings & Log** — API/model settings, usage totals, connectors, safety and logs.

## Source/regression testing

The packaged v0.7.5 Stability Fix source discovers **185 tests** in this build environment. All runnable tests pass; **57 backend-dependent tests are skipped** here because the user's real translationCore/Windows Paratext/Logos environment is not mounted. The exact packaged ZIP is re-extracted and retested before release.

For Windows certification, continue using a disposable copy of the translationCore backend and separately field-test both Paratext and Logos connectors on the target computer.

---

## v0.7.4 Paratext baseline retained below

## translationCore AI Bridge v0.7.4 — Paratext Live Connector

Windows desktop companion for translationCore Bible translation projects. The Bridge combines deterministic translationCore-compatible data handling with AI-assisted alignment, Translation Notes/Words review, QA, terminology and evidence gathering while keeping the reviewer as final authority.

## v0.7.4 focus

v0.7.4 adds a **live local Paratext 9.5 connector** while preserving the v0.7.3 Alignment Reliability architecture.

```text
translationCore project
        │
        ▼
translationCore AI Bridge (Python/Tk)
        │
        │ Windows named pipe — local computer only
        ▼
AI Bridge Paratext Connector (.ptxplg)
        │
        ▼
Official Paratext Plugin API
        │
        ▼
Paratext 9.5
```

Targeted field-test version: **Paratext 9.5.110.1**.

## Live Paratext capabilities

- current Paratext user;
- active Paratext project, project ID and language;
- current Scripture reference and scroll/sync group;
- selected Scripture text and nearby context;
- Bridge → Paratext verse navigation;
- Paratext → Bridge verse navigation;
- direct Project Notes on exact selected text;
- verse-level Project Notes when no text selection is supplied;
- explicit translationCore↔Paratext project binding;
- optional forwarding of Needs Discussion / Reject reviewer comments.

**Scripture writing is disabled in the connector.** There is no `PutUSFM`, `PutUSFMTokens`, or `PutUSX` command.

## Install the Paratext connector

1. Extract the v0.7.4 package.
2. Run `diagnose_paratext_connector.bat` if you want to check prerequisites.
3. Close Paratext completely.
4. Run `install_paratext_connector.bat`.
5. Restart Paratext and open the target Scripture project.
6. Put its Scripture window in scroll/sync group A–E.
7. Start the Bridge.
8. Open **Production → Paratext**.
9. Click **Connect / Refresh**.
10. Click **Verify / Bind Project**.
11. Enable **Sync verse navigation** if desired.

If Paratext is not auto-detected:

```bat
install_paratext_connector.bat "C:\Program Files\Paratext 9"
```

Use the actual folder containing `Paratext.exe`.

See `paratext_connector/INSTALL_WINDOWS.md` for the full procedure.

## Why compile the connector on the Paratext computer?

The Windows builder references the PluginInterfaces assembly from the **installed Paratext** and produces `translationCoreAIBridge.ptxplg` locally. This is safer for the initial field release than claiming a plugin binary built against an unverified interface version. No Visual Studio project is required by our builder; it attempts to use the Windows .NET Framework C# compiler already available on the machine.

## Project binding safety

Live notes and synchronized navigation require a stored per-translationCore-project Paratext project ID. If the active Paratext project does not match:

```text
Bridge binding: PROJECT MISMATCH
```

and the Bridge blocks the live action rather than guessing.

## Alignment reliability

The v0.7.3 architecture remains unchanged:

```text
AI linguistic links
      ↓
deterministic Alignment Compiler
      ↓
strict translationCore validator
      ↓
human review
      ↓
approved project data
```

Existing completed/human work remains protected. `Fill Alignment Gaps` is the normal AI workflow; `Audit Existing Alignment` is read-only.

## Main workspaces

- **Dashboard** — exception-first project review.
- **Alignment** — manual alignment, gap-fill AI, audit, diagnostics, approval.
- **AI Final Review** — TN/TW and QA evidence with human decisions.
- **Quality Queue** — deterministic/AI issues and audited Scripture correction.
- **tC Check State** — native translationCore selections/comments/invalidation state.
- **Knowledge Base** — TN/TA/TW/TWL/source/reference evidence.
- **Terminology** — trusted terminology decisions and analytics.
- **Psalms QA** — candidate structure/parallelism QA.
- **Production** — recovery, Git, team roles, reports, Existing Work Scan, Paratext Notes and Live Connector.
- **Settings & Log** — AI/model/Paratext settings and diagnostics.

## Windows certification

Run against your translationCore root:

```bat
certify_windows.bat "C:\Users\Benz\translationCore"
```

v0.7.4 test discovery is **152 tests: 118 core/data + 34 isolated Tk GUI**. The certifier uses a disposable clone for write-capable translationCore tests.

Then separately certify the live connector using `paratext_connector/INSTALL_WINDOWS.md`, because the plugin must be compiled/loaded against the actual Paratext installation.
