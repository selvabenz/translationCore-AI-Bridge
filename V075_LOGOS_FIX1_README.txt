translationCore AI Bridge v0.7.5 — Logos Fix 1 + Fieldset UI
2026-08-17

This patch is based on v0.7.5-certfix1.

LOGOS CONNECTOR
- Keeps Windows-local Logos COM integration and the existing NavigationBroker.
- Replaces PowerShell late-bound calls on Logos-specific COM interfaces with an in-process
  C# raw-IDispatch shim hosted by the hidden PowerShell STA helper.
- This targets the field failure where GetOpenPanels() raised TYPE_E_LIBNOTREGISTERED even
  though LogosCom.exe existed, the Logos TypeLib registry key was present, and LoadTypeLibEx
  returned S_OK.
- Connection status now distinguishes Logos detected from Navigation ready.
- Sync is refused when ApiVersion/Bible DataTypes/panel API health checks fail.
- No network listener, Logos credential, or Scripture-writing operation is added.

UI
- Production and Settings & Log collapsible headers are now compact, left-aligned
  fieldset-style legends with a disclosure arrow and horizontal rule.
- Expanded section bodies retain a subtle framed boundary.
- Collapsed sections shrink to the legend row and keep their persisted state.

TESTS IN BUILD ENVIRONMENT
- Python compile/import: PASS
- Full unittest discovery under virtual display: 175 discovered / 118 passed / 57 skipped / 0 failed
- Production/Settings fieldset layout visually checked at 1000x650 and responsive tests at 760x560.

WINDOWS FIELD TEST STILL REQUIRED
The build environment has no Logos Desktop COM server. Run certify_windows.bat as usual, then
open Logos with a Bible resource and test Bridge → Logos, Logos → Bridge, Paratext → Logos,
and Logos → Paratext navigation with verse sync enabled.
