# Logos Live Verse Navigation — v0.7.5

## Safety boundary

The Logos connector is navigation-only. It does not send Scripture text for modification, does not store Logos credentials, and does not open a TCP/HTTP listener.

## Architecture

```text
Bridge UI
   │
   ▼
NavigationBroker
   │
   ├── Paratext local named pipe → Paratext Plugin API
   │
   └── hidden persistent PowerShell 5.1 STA helper
          └── in-process C# TypeLibConverter/imported Logos4Lib interfaces
                 └── Windows Logos COM API
```

The PowerShell helper communicates with Python only through redirected stdin/stdout. Windows field diagnostics showed that simple PowerShell COM binding could obtain `Launcher.Application` but failed on richer Logos-specific COM interfaces. The current helper therefore loads the installed `LogosCom.exe` type library in memory with .NET `TypeLibConverter`, discovers the actual imported interfaces supported by the COM objects, and invokes the typed interface members. No cached/fabricated interop DLL path is required.

The confirmed field configuration reports `ILogosLauncher`, `ILogosApplication`, COM API version 3, a real Bible panel and a current Scripture reference.


## Connection health

`Connected` now means **navigation ready**, not merely “the Launcher.Application object exists.” The helper separately reports whether Logos was detected and verifies:

- `Application.ApiVersion` is readable;
- `Application.DataTypes` is available;
- the `Bible` data type is available;
- `GetOpenPanels()` can cross the COM boundary.

If Logos is running but one of those checks fails, the UI shows **Logos detected · Navigation unavailable** and refuses to enable verse sync.

## Direction and loop handling

Any connected application may be the origin:

- Bridge → Paratext + Logos
- Paratext → Bridge → Logos
- Logos → Bridge → Paratext

The broker normalizes the reference and tracks recent outbound targets. A connector reporting the exact reference that the Bridge just sent is treated as an echo. Repeated polling of the same reference is ignored. The originating connector is never immediately sent its own change back.

A short settling guard also suppresses the connector's *previously observed* verse if it is polled again immediately after the Bridge sends a different verse. This prevents an old Logos/Paratext state from bouncing the review back while navigation is still settling. The guard expires quickly, and confirmation of the requested verse removes the guard immediately so a later human navigation is accepted.

Rapid outbound Logos changes are coalesced. If the reviewer moves 1:5 → 1:6 → 1:7 while Logos is still processing 1:5, the pending target becomes 1:7 rather than forcing all intermediate requests to replay.

## Project/reference safety

- Paratext-originated navigation still requires the existing per-project Paratext project binding.
- Logos has no translationCore project identity. The Bridge therefore changes projects only when a loaded translationCore project matches the incoming canonical book ID.
- If multiple loaded translationCore projects match the same Logos book and the current project is not already one of them, the Bridge refuses to guess and asks the reviewer to select the intended project manually.
- If no matching project is loaded, the Bridge does not switch and reports the condition.
- Logos subverse references such as `5a` fall back to verse `5` only when the translationCore project has no exact `5a` verse.
- Unsaved alignment edits continue to use the existing discard confirmation before an external navigation can replace the current verse.

## Stability hardening

- The navigation broker rolls back to the real Bridge reference when an external candidate is rejected instead of remaining logically ahead of the UI.
- A rejected unchanged external reference stays quiet until relevant Bridge context changes; then it can be retried safely.
- Each Logos helper process generation owns its own response queue and stderr buffer, preventing stale threads from contaminating a restarted helper.
- Cold helper startup has a longer timeout than steady-state polling because the first in-memory COM type-library import can be slower on antivirus-scanned Windows systems.
- A named Windows mutex allows only one Bridge process to own external navigation at a time.
- Cross-application synchronization is **reference-label based**. Paratext independently resolves the label using its project versification and Logos independently resolves it using its Bible data type. Detectable Paratext label mismatches fail closed; reviewers should still verify known versification-sensitive passages because matching labels do not prove textual equivalence across versification systems.

## Field test matrix

Test on Windows with the exact packaged build:

1. Logos closed at Bridge startup.
2. Logos open before Bridge startup.
3. Logos COM component unavailable/unregistered.
4. No Bible panel open.
5. Bible panel active; commentary panel active; multiple Bible panels open.
6. Bridge → Logos navigation for OT/NT and numbered books.
7. Logos → Bridge navigation.
8. Paratext → Bridge → Logos.
9. Logos → Bridge → Paratext.
10. Rapid Next Verse actions.
11. Both external applications changed nearly simultaneously (last accepted observation wins; no loop).
12. Logos restart while sync is enabled.
13. Bridge project does not contain the Logos book.
14. Subverse reference (`1a`) and a normal verse range/current-range start.
15. Small-screen Production page with both Paratext and Logos sections expanded.
16. Close Bridge while a Logos COM operation is pending; no orphan visible console window.

Real Windows COM execution cannot be certified from the Linux source-build environment.
