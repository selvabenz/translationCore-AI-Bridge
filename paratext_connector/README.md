# translationCore AI Bridge — Paratext Live Connector v0.7.4

This folder contains the first complete **source/build/install package** for the local Paratext companion used by translationCore AI Bridge v0.7.4.

## Target

Field-test target: **Paratext 9.5.110.1 on Windows**.

The installer compiles the connector on the user's Windows computer against the `PluginInterfaces` assembly shipped with that installed Paratext. This avoids shipping a connector compiled against a possibly different Paratext interface version.

## What it does

The plugin starts automatically with Paratext and creates the local named pipe:

```text
\\.\pipe\translationCoreAIBridge
```

Supported commands are intentionally limited to:

- `get_state` — current Paratext user, active project/project ID/language, reference, scroll group and Scripture selection/context.
- `set_reference` — move the active Paratext scroll/sync group to a Scripture reference.
- `create_note` — create a **Paratext Project Note** anchored to the exact selected Scripture text (or to the verse when no selection is supplied).

There is **no Scripture write command**. The connector does not call `PutUSFM`, `PutUSFMTokens`, or `PutUSX`.

## Install — recommended

1. Close Paratext completely.
2. From the v0.7.4 root folder, double-click `install_paratext_connector.bat`.
3. The installer detects Paratext 9, finds its PluginInterfaces assembly, compiles the connector with the Windows .NET Framework compiler, and copies:

```text
<Paratext install>\plugins\translationCoreAIBridge\translationCoreAIBridge.ptxplg
```

4. Restart Paratext.
5. Open the Scripture project you want to connect.
6. Put the active Scripture window into Paratext scroll/sync group **A–E**.
7. Start translationCore AI Bridge.
8. Go to **Production → Paratext** and click **Connect / Refresh**.
9. Click **Verify / Bind Project** to bind the current translationCore project to that Paratext project ID.
10. Enable **Sync verse navigation** if desired.

## If auto-detection fails

Run:

```bat
diagnose_paratext_connector.bat
```

or provide the Paratext installation explicitly:

```bat
install_paratext_connector.bat "C:\Program Files\Paratext 9"
```

Use the actual folder containing `Paratext.exe` if yours is different.

## Direct Project Notes

For the safest selected-text note workflow:

1. Navigate Bridge and Paratext to the same verse.
2. Select the exact target-language phrase in Paratext.
3. Click **Connect / Refresh** so the selection is visible in the Bridge.
4. Click **Sync Notes** and enter the reviewer comment.

If selected text occurs more than once and the connector cannot prove which occurrence is intended, it fails closed and asks you to select the exact occurrence in Paratext.

The note's actual author is the current registered Paratext user. AI-originated content is visibly prefixed `[AI Suggestion]`; the connector does not impersonate a Paratext project member.

## Project binding safety

Live note creation and synchronized navigation require an explicit per-translationCore-project binding to the active Paratext project ID. If Paratext later has a different project active, the Bridge reports **PROJECT MISMATCH** and blocks the live action.

## Build only

```bat
build_paratext_connector.bat
```

Output:

```text
paratext_connector\dist\translationCoreAIBridge.ptxplg
```

## Uninstall

Close Paratext, then run:

```bat
uninstall_paratext_connector.bat
```

## Source files

- `AiBridgeConnectorPlugin.cs` — Paratext Plugin API adapter.
- `NamedPipeBridgeServer.cs` — local-only transport.
- `BridgeProtocol.cs` — JSON protocol models.
- `build_connector.ps1` — compiler/Paratext interface discovery.
- `install_connector.ps1` — safe installation into Paratext's plugins folder.
- `uninstall_connector.ps1` — removal.
- `diagnose_connector.ps1` — Windows diagnostics.

See `INSTALL_WINDOWS.md` and `PROTOCOL.md` for details.
