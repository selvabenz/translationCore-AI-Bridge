# Windows Certification Checklist — v0.7.4

## A. Source/runtime regression

Run:

```bat
certify_windows.bat "C:\Users\Benz\translationCore"
```

Expected discovery/result when all tests pass:

```text
WINDOWS CERTIFICATION RESULT: 152/152 TESTS PASSED
  Core/data tests: 118/118
  Isolated Tk GUI tests: 34/34
```

The certifier must report that write-capable translationCore tests use only the disposable clone.

## B. Paratext connector diagnostics

With Paratext installed, run:

```bat
diagnose_paratext_connector.bat
```

Confirm:

- Paratext installation found;
- version reports 9.5.110.1 for the targeted first certification;
- PluginInterfaces assembly found;
- Windows .NET Framework C# compiler found.

## C. Build/install connector

1. Close Paratext completely.
2. Run:

```bat
install_paratext_connector.bat
```

3. Confirm `PARATEXT CONNECTOR INSTALLED`.
4. Confirm the installed file exists under:

```text
<Paratext>\plugins\translationCoreAIBridge\translationCoreAIBridge.ptxplg
```

## D. Paratext load

1. Start Paratext.
2. Open the target Scripture project.
3. Put the Scripture window in scroll/sync group A.
4. Start the Bridge.
5. Production → Paratext → Connect / Refresh.

Expected:

```text
● Connected
Paratext 9.5.110.1
Connector 0.7.4
actual Paratext user
active project
current reference
Group A
```

## E. Project binding safety

1. Click **Verify / Bind Project** and confirm `Bound ✓`.
2. Switch Paratext to a different project.
3. Refresh.
4. Confirm Bridge shows `PROJECT MISMATCH`.
5. Confirm live note/navigation action is blocked.
6. Return to the bound Paratext project.

## F. Two-way verse navigation

Enable **Sync verse navigation**.

- Bridge GEN 1:1 → GEN 1:2: Paratext follows.
- Paratext GEN 1:2 → GEN 1:3: Bridge follows.
- Repeat rapidly between two verses and confirm no navigation loop.
- Change Bridge project/book to another explicitly bound book and confirm correct Paratext navigation.

## G. Selected-text Project Note

1. Select an exact Tamil phrase in Paratext.
2. Connect / Refresh and confirm Bridge displays the exact selection.
3. Sync Notes.
4. Confirm the note marker appears on that exact text.
5. Confirm note author is the actual Paratext user and content identifies `[AI Suggestion]` when sent as AI-originated content.

### Repeated-word edge case

Choose a verse where the same Tamil word occurs twice.

- With the exact occurrence selected in Paratext, note must attach to that occurrence.
- Without a resolvable exact occurrence/context, Bridge must fail instead of attaching to the wrong word.

## H. Reviewer-decision forwarding

Enable **Auto-send review notes**.

- Needs Discussion: local Bridge decision saves first, then a Paratext note is created.
- Reject AI: same.
- Disconnect/close Paratext and repeat: local Bridge decision must still save; live-note failure must not erase it.

## I. Scripture-write boundary

Verify normal Paratext Scripture text does not change during:

- Connect / Refresh;
- navigation sync;
- selected-text note creation;
- Needs Discussion/Reject forwarding.

The connector exposes Project Notes only; any Scripture change is a certification failure.

## J. Packaged EXE/installer

After source/connector testing:

```bat
build_windows_installer.bat
```

Install the Setup EXE on a clean Windows test machine. Confirm the Start menu includes connector install/uninstall actions and the packaged Bridge can connect after the plugin is installed into Paratext.
