translationCore AI Bridge v0.7.5
Logos Navigation + Responsive UX

Baseline: v0.7.4-paratext-buildfix4

New:
- local Logos Desktop verse navigation through Windows COM
- any-direction Bridge / Paratext / Logos navigation broker with echo protection
- latest-wins non-blocking Logos navigation/polling
- Dashboard exception details side-by-side with queue
- Workspace sidebar removed; User Guide moved to Help
- tN tW Review renamed/reordered before Alignment
- cleaner Alignment workflow toolbar
- screen-aware tooltips
- collapsible Production and Settings sections
- Bridge-recorded lifetime token + estimated-cost totals

Preserved:
- v0.7.4 Paratext Live Connector and Project Notes behavior
- deterministic v0.7.3+ alignment compiler and strict validation
- existing-work protection and stale guards
- no automatic Scripture writes

Portable test result in build environment:
173 discovered / 116 passed / 57 backend-dependent skipped / 0 failed.

Important: real Logos COM, Paratext 9.5.110.1, Windows EXE, installer, and live project certification must be completed on the target Windows computer.

CERTIFICATION FIX 1 (2026-08-17)
--------------------------------
Windows field certification exposed one stale v0.6 responsive-GUI assertion that still
expected the former compact tab order (Dash / ... / AI Review) and the removed Workspace
sidebar. The runtime UI was behaving as designed for v0.7.5; the obsolete certification
assertion stopped the suite before the remaining GUI tests could run.

This certfix updates only that regression test to the intentional v0.7.5 invariants:
Dash / tN-tW / Align compact navigation, no Workspace sidebar, visible status/usage and
Alignment controls at 760x560. No production code, Paratext protocol, Logos navigation,
project data, or Scripture write behavior is changed.



LOGOS FIX 1 + FIELDSET UI (2026-08-17)
---------------------------------------
Field diagnostics proved the installed Logos type library was present and loadable, while
PowerShell late binding still failed on Logos-specific COM return interfaces. The Logos helper
now hosts a small C# raw-IDispatch shim and verifies navigation readiness before calling the
connection healthy.

Production and Settings & Log collapsible sections now use compact left-aligned fieldset-style
legends instead of full-width centred header buttons.

Build-environment full virtual-display result: 175 discovered / 118 passed / 57 skipped / 0 failed.
Real Logos navigation must still be verified on Windows with Logos running.
