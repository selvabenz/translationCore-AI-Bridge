translationCore AI Bridge v0.7.5 - Logos Fix 4

Purpose
-------
Fixes Logos live verse navigation on Windows installations where the Logos COM launcher
is available but late-bound PowerShell/raw IDispatch cannot expose LogosApplication.ApiVersion
or other richer Logos COM interfaces.

What changed
------------
- logos_bridge.ps1 now imports the installed Logos Bible Software 4 Type Library at runtime
  with .NET TypeLibConverter.
- Logos application, panel, reference and navigation calls are invoked through the generated
  COM-imported interface metadata instead of PowerShell late binding or hand-written IDispatch.
- The imported interop assembly is cached under the current user's LocalAppData and keyed to
  the installed LogosCom.exe size + timestamp, so a Logos update automatically creates a new
  cache entry.
- No Logos credentials, network listener, registry edits or Scripture writes are introduced.
- Existing Paratext sync and v0.7.5 UI/navigation-broker behavior are unchanged.

Windows field test
------------------
1. Start Logos and open a Bible resource at a normal verse.
2. From this application folder run:
   powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File ".\logos_connector\logos_bridge.ps1"
3. Enter exactly:
   {"action":"state"}
4. A healthy result should report ok=true, navigation_ready=true and api_version=3 (or higher),
   plus the current Bible reference when a Bible panel is open.
5. Then run the Bridge and test Bridge -> Logos, Logos -> Bridge, and Paratext -> Bridge -> Logos.

The Linux build environment cannot execute the Windows Logos COM API, so real Logos behavior
still requires Windows field certification.
