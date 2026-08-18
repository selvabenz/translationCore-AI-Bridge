# Logos Live Verse Navigation — v0.7.5

translationCore AI Bridge uses the Windows Logos COM API through a small local PowerShell STA helper that hosts an in-process C# `IDispatch` shim.

- No Logos username, password, API key, or network listener is used.
- The helper connects to `LogosBibleSoftware.Launcher` and uses the documented COM `Application` object.
- Logos-specific COM interfaces are invoked through raw `IDispatch` instead of PowerShell late binding. This avoids a Windows/PowerShell failure observed in the field where `GetOpenPanels()` raised `TYPE_E_LIBNOTREGISTERED` even though `LogosCom.exe` and the Logos type library were correctly registered and directly loadable.
- Navigation uses `DataTypes.GetDataType("Bible").ParseReference`, `CreateNavigationRequest`, and `Navigate`.
- Reading the current location uses `GetActivePanel` / `GetOpenPanels` and `GetCurrentReferencesAndHeadwords`.
- The Bridge polls the reference and applies echo suppression so Logos, Paratext, and the Bridge can all be navigation origins.
- Logos is never used to write Scripture or project data.

The connector is Windows-only and requires the Logos desktop application with its COM type library registered.

## Readiness semantics

The Bridge distinguishes **Logos detected** from **Navigation ready**. A launcher/application object alone is not considered sufficient. The connector verifies `ApiVersion`, Bible `DataTypes`, and the richer panel API before allowing the sync checkbox to remain enabled.
