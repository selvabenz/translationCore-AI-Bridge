# translationCore AI Bridge v0.7.0 — Reviewer Precision & Language-Aware Workflow

v0.7.0 concentrates on the three things that matter most during field review: **reviewer speed, lower AI noise, and less UI friction**, while adding language-aware behavior and Paratext-compatible reviewer-note export.

## Reviewer speed

- Added **F5** for AI Full Verse Review.
- Added **F8 Next Priority** to open the highest-priority exception and fall back to the next verse.
- Added reviewer decision shortcuts: **Ctrl+Enter Accept**, **Ctrl+Shift+D Needs Discussion**, **Ctrl+Shift+R Reject AI**.
- Added **Ctrl+Shift+Right** for next verse.
- Added optional **Auto-advance** after human decisions.
- Preserved changed-only chapter review, batch review and exception-first queue.

## AI accuracy and false-positive reduction

- Added a deterministic post-AI evidence/confidence gate.
- Very low-confidence findings are kept out of the main queue but retained in the saved review for audit.
- Duplicate findings for the same underlying issue are collapsed to the strongest evidence-backed item.
- Critical/High findings that fail confidence/evidence thresholds are downgraded instead of being presented as authoritative severe errors.
- Uncertain TN/TW verdicts are normalized to `review` rather than overconfident pass/problem conclusions.
- Prompts explicitly require the strongest plausible target-language interpretation to be considered before flagging omission/addition/error.

## Language/plugin architecture

- Target language detection is project-aware: manifest/project metadata first, Unicode script fallback second.
- Source language is detected from source tokens (Hebrew/Greek), with canon fallback.
- Bundled target plugins: Tamil, Hindi, Malayalam, Telugu, Kannada, Gujarati, Bengali and Punjabi, plus a generic safe plugin.
- Active plugin now controls source/target labels, fonts, language-specific QA categories and AI prompt guidance.
- Tamil-specific Sandhi rules are not applied to non-Tamil projects.

## Paratext-compatible reviewer notes

- Reviewer comments can now be mirrored into **Paratext Notes 1.1-compatible XML**.
- Notes are kept in the companion area and can be exported from Production.
- The XML includes thread, verse selection and timestamped comment/content structures.
- This release provides compatible exchange XML; it does not automatically authenticate/post notes to a Paratext server.

## UI / truncation fixes

- Review and QA toolbars reflow at narrow widths.
- Horizontal/vertical scrolling was audited across major display areas.
- Added/retained scrollbars for Dashboard analysis, exceptions, source/target tokens, alignment groups, AI Proposal, Result + Evidence, Knowledge Base, Quality Queue, tC state, terminology, Psalms QA, metrics, logs, Git diff and privacy manifest.
- TN/TW selection editor now has horizontal and vertical scrolling.
- Terminology-rule text fields now have vertical scrollbars.
- Universal horizontal navigation is available on overflow-capable text/list/tree controls.

## Color-coded AI Proposal

- source language — purple;
- target language — teal/green;
- English rationale — slate/gray;
- confidence — green/high, amber/medium, red/low.

The labels are generated from the detected project language context rather than being fixed to Hebrew/Tamil.

## Branding

The user's supplied official AI Bridge logo is now used for the release app/EXE/installer/user-guide icon assets.

## Regression discovery

v0.7.0 contains **99 production tests**:

- 75 core/data/production tests;
- 24 real-Tk GUI tests isolated into fresh Python processes by the Windows certifier.

Run:

```bat
certify_windows.bat "C:\path\to\translationCore"
```

before rebuilding/distributing the Windows installer.
