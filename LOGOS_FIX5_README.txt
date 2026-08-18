translationCore AI Bridge v0.7.5 - Logos Fix 5

Purpose
-------
Fix the Logos COM connector after field diagnostics showed that Fix 4 successfully
loaded the installed Logos type library but incorrectly assumed imported coclass/type
names and reported a cache DLL path that was never persisted.

Changes
-------
* Keeps the Logos type library import in memory; no phantom cached interop DLL path.
* Discovers the actual COM interfaces supported by each Logos RCW at runtime using
  Marshal.QueryInterface against imported interface GUIDs.
* Resolves Application, ApiVersion, DataTypes, panels, references, navigation requests,
  and collection members from those compatible interfaces rather than hard-coding
  LogosLauncher/LogosApplication imported type names.
* Adds a read-only {"action":"diagnose"} helper action that reports the compatible
  launcher/application interface names if another machine-specific COM edge case appears.
* Preserves ASCII-only PowerShell 5.1 compatibility and stderr diagnostics.
* Does not change Paratext integration, Project Notes, project data, or Scripture.

First Windows test
------------------
Keep Logos open with a Bible resource visible, then run:

  powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File ".\logos_connector\logos_bridge.ps1"

Enter:

  {"action":"state"}

If navigation_ready is false, also enter:

  {"action":"diagnose"}

Send both JSON responses for diagnosis.
