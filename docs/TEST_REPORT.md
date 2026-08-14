# Production Regression Test Report — v0.7.0

## Scope

v0.7.0 changes reviewer navigation, AI post-processing, language/plugin behavior, reviewer-note exchange, proposal rendering and overflow handling. These areas are included in the release gate rather than being treated as cosmetic-only changes.

Current discovery contains **99 tests**:

- **75 core/data/production tests**
- **24 real-Tk GUI tests**, each isolated into a fresh Python process by the Windows certification runner

## New v0.7.0 coverage

The new regression tests verify:

1. low-confidence AI findings are suppressed from the priority queue but retained for audit;
2. duplicate AI findings collapse to the strongest instance;
3. project language detection recognizes manifest/script evidence and chooses a target plugin;
4. source detection distinguishes Hebrew/Greek source evidence;
5. a real Tamil project resolves Tamil target + Biblical Hebrew source;
6. Paratext Notes 1.1-compatible XML is written without modifying Scripture;
7. official v0.7.0 logo/icon assets are packaged;
8. language-dependent UI labels/fonts and reviewer shortcut bindings exist;
9. AI Proposal has separate source/target/English/confidence color tags;
10. review/QA action areas reflow on compact windows;
11. overflow-prone display areas expose horizontal/vertical navigation;
12. existing human alignment cannot be silently remapped by automatic preparation;
13. prior v0.6 production transactions, TN/TW sync, rollback, Git, recovery, reporting, security and responsive tests remain green.

## Real-backend execution in the build environment

Against the supplied Ruth/Psalms/Obadiah/Genesis-capable translationCore backend fixture:

- **75/75 core/data/production tests passed** against a disposable clone of the supplied real backend fixture.
- **24/24 GUI tests passed** individually in fresh Xvfb-backed Python/Tk processes.
- **99/99 release tests passed** in the build environment using the same core/isolated-GUI separation as the Windows certifier.
- Python compile-all/import checks pass.

The authoritative Windows release gate is the included Windows certifier because it validates actual Python 3.11/3.12 + Tk 8.6 behavior and Windows process semantics.

## Required Windows release gate

Run on Windows:

```bat
certify_windows.bat "C:\path\to\translationCore"
```

Expected result:

```text
WINDOWS CERTIFICATION RESULT: 99/99 TESTS PASSED
  Core/data tests: 75/75
  Isolated Tk GUI tests: 24/24
```

The certifier must display a non-empty disposable test-copy path under `%TEMP%`. Live translationCore projects are never permitted to be write targets for automated certification.

## Paratext notes scope

Automated tests validate Notes 1.1 exchange structure and Scripture non-modification. This release does **not** certify direct Paratext-server authentication/posting; it creates/export compatible XML for controlled exchange/import or future API integration.
