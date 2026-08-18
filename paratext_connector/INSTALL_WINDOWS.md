# Paratext Live Connector — Windows Installation

Targeted field-test environment: **Paratext 9.5.110.1**.

## 1. Diagnose first (optional but useful)

Close nothing yet and run:

```bat
diagnose_paratext_connector.bat
```

A ready system should report:

```text
Paratext installation: ...
Paratext file version: 9.5.110.1...
PluginInterfaces assemblies: found
.NET Framework C# compiler: found
DIAGNOSTIC RESULT: READY TO BUILD/INSTALL CONNECTOR
```

## 2. Close Paratext

The plugin cannot safely be replaced while Paratext has it loaded. Exit Paratext completely.

## 3. Install

From the v0.7.4 folder run:

```bat
install_paratext_connector.bat
```

If Paratext cannot be discovered automatically:

```bat
install_paratext_connector.bat "C:\Program Files\Paratext 9"
```

The script may request administrator permission only for the final copy into a protected Program Files folder.

Successful output ends with:

```text
PARATEXT CONNECTOR INSTALLED
Installed: ...\plugins\translationCoreAIBridge\translationCoreAIBridge.ptxplg
```

## 4. Start Paratext

Open the target Scripture project and put the Scripture window in scroll/sync group **A**, **B**, **C**, **D**, or **E**. The Bridge deliberately refuses to choose a group silently.

## 5. Connect the Bridge

In translationCore AI Bridge:

**Production → Paratext → Connect / Refresh**

Expected state:

```text
● Connected · Paratext 9.5.110.1 · Connector 0.7.4
User: <Paratext user> · Project: <project> · Reference: GEN 1:1 · Group A
Bridge binding: Not bound
```

## 6. Bind the project

Click **Verify / Bind Project** and confirm. This records the active Paratext project ID for the current translationCore project. It is a safety mapping; it does not change Scripture.

Expected:

```text
Bridge binding: Bound ✓
```

## 7. Test two-way navigation

Enable **Sync verse navigation**.

- Change verse in the Bridge → Paratext should follow.
- Change verse in Paratext → the matching bound translationCore book project should follow.

An origin/request guard prevents normal Bridge-originated navigation from echoing back indefinitely.

## 8. Test selected-text notes

1. In Paratext select a target-language phrase in the current verse.
2. Click **Connect / Refresh** in the Bridge and confirm the Selection line shows the same phrase.
3. Click **Sync Notes**.
4. Enter a test reviewer note.
5. Confirm the normal Project Note marker appears on that selected text in Paratext.

If the phrase occurs several times, select the exact occurrence in Paratext. The connector refuses ambiguous attachment rather than guessing.

## Safety boundary

v0.7.4 supports:

```text
READ: user / project / project ID / language / reference / selection
NAVIGATE: set reference in the active Paratext sync group
WRITE: Project Notes only
```

It does not expose Scripture-editing commands.
