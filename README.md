# translationCore AI Bridge v0.7.0 — Reviewer Precision & Language-Aware Workflow

Windows desktop companion for translationCore projects. AI performs repetitive resource retrieval, source-language analysis, alignment preparation, Translation Notes/Words target selection, terminology comparison and first-pass QA; human reviewers remain authoritative for Scripture edits, check approval, terminology and final approval.

## v0.7.0 focus

This release is intentionally about **reviewer throughput, precision and language awareness** rather than adding another large group of checking tools.

### 1. Reviewer speed
- F5 runs AI Full Verse Review.
- F8 opens the next highest-priority exception, then falls back to the next verse.
- Ctrl+Enter accepts the selected AI check result.
- Ctrl+Shift+D records Needs Discussion.
- Ctrl+Shift+R rejects the selected AI conclusion.
- Ctrl+Shift+Right moves to the next verse.
- Optional **Auto-advance** moves to the next priority item after a human decision.
- Changed-only chapter review and the project-wide exception queue remain the default fast path.

### 2. AI accuracy / false-positive reduction
A deterministic post-AI review gate now:
- suppresses very low-confidence findings from the main reviewer queue;
- downgrades Critical/High claims that do not meet confidence/evidence thresholds;
- removes duplicate findings for the same underlying problem;
- turns uncertain TN/TW pass/problem claims into `review` rather than overstating certainty;
- keeps suppressed findings in the saved AI review for audit rather than deleting them.

The model prompt also requires the strongest reasonable target-language explanation to be considered before reporting omission/addition/error, and asks the model not to repeat one issue under multiple labels.

### 3. UI friction / overflow
- Review, QA and alignment toolbars reflow on narrow windows.
- Important text viewers have vertical and/or horizontal scrolling according to their content.
- Long evidence, logs, Knowledge Base content, terminology analytics, Psalms QA, Git diff, privacy manifests and token/group lists can be fully inspected without truncation.
- The TN/TW selection editor and terminology editor now have scrollable fields too.
- Shift+mouse-wheel and horizontal navigation are supported where relevant.

### 4. Language/plugin architecture
The active project is inspected at runtime. The target language is resolved primarily from project/manifest metadata and secondarily from Unicode script evidence. The source language is detected from source tokens (Hebrew/Greek) with canon fallback.

Bundled target plugins include Tamil, Hindi, Malayalam, Telugu, Kannada, Gujarati, Bengali and Punjabi plus a safe generic plugin. The detected plugin controls:
- source/target labels and fonts;
- language-specific QA categories;
- prompt guidance;
- alignment/review terminology;
- target-language editorial checks.

Tamil-specific Sandhi/word-joining checks are therefore not blindly applied to a Hindi, Malayalam or other project.

### 5. Paratext-compatible reviewer notes
Reviewer comments associated with AI/tC review decisions can also be written as **Paratext Notes 1.1-compatible XML** under the companion area:

```text
.apps/translationCoreAI/paratextNotes/<book>.notes.xml
```

The application can export that XML from the Production workspace. Direct authenticated posting into a Paratext server/project is deliberately not claimed in this release; the output is a compatible exchange file.

### 6. Color-coded AI Proposal
The AI alignment proposal now visually separates evidence roles:
- **source language** (e.g. Hebrew) — purple;
- **target language** (e.g. Tamil) — teal/green;
- **English rationale** — slate/gray;
- **confidence** — green (high), amber (medium), red (low).

The same renderer uses the detected source/target language names, so the proposal is not hard-coded to Hebrew→Tamil.

### 7. Official product identity
The supplied official AI Bridge logo is now the release icon source for the app UI, Windows EXE, installer and user guide.

## Human authority boundary

```text
translationCore project + project-pinned Translation Helps
                         ↓
              deterministic resolver
                         ↓
                  AI preparation
                         ↓
      false-positive / confidence evidence gate
                         ↓
           evidence + proposal + priority
                         ↓
                    HUMAN REVIEW
                         ↓
          approved translationCore state
```

AI never silently rewrites Scripture, completes TN/TW, approves alignment, changes terminology, or gives final publication approval.

## Main workspaces

- **Dashboard** — project scan, project-wide exception-first queue, changed chapter/book preparation.
- **Alignment** — source `topWords` ↔ target `bottomWords`, manual/AI proposal, Undo/Redo, tC-approved save.
- **AI Final Review** — TN/TW selections, verdicts, corrections, confidence, evidence and fast-review controls.
- **Quality Queue** — deterministic + AI QA with human finding decisions and Scripture editor.
- **tC Check State** — selections, invalidations, comments, verse edits, current/stale status.
- **Knowledge Base** — project-aware TN/TA/TW/TWL/source/reference provenance.
- **Terminology** — human rules + book-level Translation Words analytics.
- **Psalms QA** — Hebrew structural/parallelism candidates and alignment-density checks.
- **Production** — recovery journal, Git, team assignments/roles, metrics, reports, security, benchmark, language/plugin status and Paratext Notes export.
- **Settings & Log** — API security, model routing, cost warning, privacy manifest and redacted diagnostics.

## Windows certification

Use 64-bit Python 3.11 or 3.12 for source/runtime certification:

```bat
certify_windows.bat "C:\path\to\translationCore"
```

The certifier creates a disposable project clone and never uses the live translationCore projects as write targets.

Expected v0.7.0 discovery:

```text
Core/data/production: 75
Isolated Tk GUI:      24
Total:                99
```

## Fresh Windows distribution

End users should receive the packaged Setup EXE; they do not need Python/Tk/Pillow/PyInstaller/Inno Setup installed. Git is optional and only affects Git checkpoint/history features.

Build on a Windows build machine:

```bat
build_windows_installer.bat
```

See `docs/WINDOWS_CERTIFICATION_CHECKLIST.md` before distributing the packaged EXE/installer.
