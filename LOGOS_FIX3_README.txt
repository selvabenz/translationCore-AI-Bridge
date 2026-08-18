translationCore AI Bridge v0.7.5 - Logos Fix 3

Focused Windows Logos COM compatibility fix.

Target-machine diagnostics proved:
- LogosBibleSoftware.Launcher can be created through PowerShell COM.
- launcher.Application works through the native PowerShell COM binder.
- raw IDispatch lookup of the same launcher Application property fails with
  DISP_E_MEMBERNOTFOUND (0x80020003).

Fix 3 therefore uses a hybrid path:
1. Native PowerShell COM binder for Launcher + Launcher.Application.
2. Raw IDispatch shim for LogosApplication and richer returned COM objects,
   avoiding the PowerShell typelib-export failure previously seen on GetOpenPanels.

No registry edits, Logos credentials, network listener, Scripture writes, or
Paratext connector changes are introduced.
