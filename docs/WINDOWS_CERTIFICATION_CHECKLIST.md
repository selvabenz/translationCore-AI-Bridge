# Windows Production Certification Checklist — v0.7.0

## Prerequisites

- [ ] Windows 10/11 64-bit.
- [ ] Python 3.11 or 3.12 (Python 3.12 recommended for source certification).
- [ ] `diagnose_windows.bat` reports Bridge 0.7.0 and a working Tk import.
- [ ] The translationCore data root contains `projects` and `resources`.

## Disposable-path safety gate

Run:

```bat
certify_windows.bat "C:\Users\Benz\translationCore"
```

Before tests begin, confirm:

```text
LIVE PROJECTS:         C:\Users\Benz\translationCore
DISPOSABLE TEST COPY:  C:\Users\Benz\AppData\Local\Temp\tc_ai_bridge_v070_cert_...\translationCore
```

Stop immediately if the disposable path is blank, equals the application directory, equals the live translationCore root, or is inside either one. The Python fixture should also issue `SAFETY REFUSAL` for such paths.

## Regression gate

v0.7.0 runs core/data tests first and then each real-Tk GUI test in a fresh Python process. Any GUI process crash or 90-second timeout fails certification.

Expected final summary for this release:

```text
WINDOWS CERTIFICATION RESULT: 99/99 TESTS PASSED
  Core/data tests: 75/75
  Isolated Tk GUI tests: 24/24
```

- [ ] No `FAIL`, `ERROR`, `Tcl_AsyncDelete`, or child-process timeout.
- [ ] Certification cleanup removes the disposable root/junction.
- [ ] `inspect_companion_windows.bat` after certification shows no certification-created changes in live project companion state.

## Application smoke gate

- [ ] Start with `run_windows.bat`.
- [ ] Load the live translationCore root.
- [ ] Test API and confirm green connected indicator.
- [ ] Check one verse Alignment and Full Verse Review.
- [ ] Check chapter Batch progress/summary.
- [ ] Resize down to 760×560 and confirm progress, token/cost and toolbars remain visible.
- [ ] Drag AI Proposal divider to both extremes; toolbar remains visible.
- [ ] Close/reopen repeatedly without Tk/Tcl cleanup errors.

## Packaged EXE/installer gate

The exact PyInstaller/Inno Setup artifacts must separately be installed and executed on Windows before labeling the binary itself production-certified.
