translationCore AI Bridge v0.7.5 - Stability Fix

Baseline: v0.7.5 Logos Fix 5 (field-confirmed Bridge + Paratext + Logos synchronization).

Hardening in this package:
- broker commit/rollback and context-aware retry for rejected external navigation
- read-only destination prevalidation before external project switching
- Logos helper generation-isolated response/stderr queues
- 10s cold helper startup timeout, 5s navigation timeout, 3.5s steady state timeout
- Windows named mutex allowing one Bridge instance to own external sync
- explicit reference-label/versification safety notice and detectable Paratext mismatch stop
- v0.7.5 Tk UI tests isolated per process in Windows certification

No Scripture-write protocol was added. Paratext Project Notes and the v0.7.4 companion protocol remain unchanged.

Run on Windows:
  certify_windows.bat "C:\Users\<you>\translationCore"

Then field-test Bridge, Paratext and Logos in all three navigation directions, including rapid navigation, connector restart, unsaved-work cancellation, no/multiple matching tC projects, and two Bridge instances.
