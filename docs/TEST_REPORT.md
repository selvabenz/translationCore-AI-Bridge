# v0.7.5 Test Report

## Portable/source result

The v0.7.5 working tree was compiled with Python `compileall` and the complete unittest suite was executed under an isolated virtual Tk display.

```text
Discovered: 173
Passed:     116
Skipped:     57
Failed:       0
```

The 57 skipped tests require the real uploaded/evolving translationCore backend or Windows-specific runtime integrations that are not available in this Linux build environment.

## New v0.7.5 coverage

- application/installer/packaging version consistency;
- Logos COM helper present in the Windows PyInstaller data bundle;
- no Logos TCP/HTTP listener, credentials or Scripture-write action;
- all standard 66 books have unique canonical mappings, with OT/NT/numbered-book reference cases checked in both directions;
- invalid Logos/Bridge references fail closed;
- NavigationBroker echo suppression, duplicate-poll suppression, stale pre-navigation-state settling, and fail-open expiry when a connector never confirms the requested verse;
- new connector-origin changes are still accepted;
- Bridge-local token/cost totals persist and accumulate;
- Workspace sidebar removal and Help/User Guide relocation;
- `tN tW Review` tab naming/order;
- Dashboard side-by-side exception queue/details layout;
- Alignment workflow toolbar and secondary `More…` actions;
- all normal action buttons have tooltips;
- tooltips remain inside the visible screen in small-window GUI tests;
- Production/Settings collapsible sections and small-screen scrolling/stacking;
- Paratext-origin navigation does not echo to Paratext but forwards to Logos;
- Logos-origin navigation does not echo to Logos but forwards to Paratext;
- Bridge-origin navigation can forward to both;
- Logos sync does not silently auto-enable on restart;
- stale Logos COM launcher/application references are recreated after a Logos restart;
- Logos background polling/navigation workers avoid Tk-root capture and unbounded worker tracking;
- multiple same-book translationCore projects are never guessed; unavailable external chapter/verse targets are validated before any project switch.

## Regression result

All runnable pre-v0.7.5 regression tests also pass, including alignment compiler invariants, strict proposal validation, Project Notes static/protocol safety, Windows packaging metadata, credential handling and Tk stability tests.

## Not certified in this environment

This report does **not** claim:

- actual Windows Logos COM execution;
- compatibility with the user's exact installed Logos Desktop build;
- actual Paratext 9.5.110.1 plugin loading/named-pipe runtime behavior;
- Windows EXE/installer execution;
- tests against the user's current live translationCore data root.

Those must be completed on the target Windows computer. The live translationCore root must never be used as a write target during automated certification; use the existing disposable-backend certification flow.
