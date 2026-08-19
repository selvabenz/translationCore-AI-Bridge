# translationCore AI Bridge

translationCore AI Bridge is a Windows desktop companion for Bible translation projects managed by [translationCore](https://translationcore.com/). It combines translationCore-compatible project handling with AI-assisted review while keeping translators and reviewers in control of every project change.

Current version: **0.7.5**

## Purpose

The application helps reviewers work through repetitive and evidence-heavy translation tasks from one desktop workspace. It can:

- discover translationCore projects, chapters, verses, checks, and installed resources;
- prepare source-to-target word alignment proposals;
- collect Translation Notes, Translation Words, Translation Academy, and source-language evidence;
- run deterministic and AI-assisted quality checks;
- support terminology review, Psalms QA, reporting, and project-wide exception queues;
- synchronize verse navigation with Paratext and Logos Desktop on Windows;
- record reviewer decisions, comments, metrics, recovery data, and Git checkpoints.

AI is an assistant, not a project authority. It may prepare evidence and proposals, but it cannot silently rewrite Scripture, approve alignment, complete TN/TW checks, change terminology, or grant final approval. Project-changing actions require an explicit human decision and pass through validation and transaction safeguards.

## Features at a glance

- **Project dashboard** - discovers translationCore projects and provides changed-only, exception-first review queues.
- **TN/TW review** - gathers Translation Notes and Translation Words evidence for human accept, discuss, or reject decisions.
- **Word alignment** - supports manual many-to-many alignment, AI gap filling, read-only audits, undo/redo, and human approval.
- **Existing-work protection** - preserves completed and partially completed alignments and rejects stale or conflicting AI results.
- **Quality review** - combines deterministic checks with structured AI review, confidence gates, deduplication, and false-positive suppression.
- **Scripture correction** - provides explicit human-authorized editing with validation, backups, transaction recovery, and stale-state propagation.
- **tC check state** - reads and updates native selections, comments, invalidations, completion state, and verse edits.
- **Knowledge base** - connects project-pinned TN, TA, TW, TWL, source-language, morphology, and reference evidence with provenance.
- **Terminology tools** - records trusted terminology decisions and reports book-level Translation Words consistency and exceptions.
- **Language-aware workflow** - detects source and target languages and applies appropriate labels, fonts, prompts, and editorial checks.
- **Psalms QA** - identifies candidate structural, parallelism, source-pattern, and alignment-density issues for review.
- **Paratext integration** - supports project binding, two-way verse navigation, Project Notes, Notes 1.1 XML, and explicit note synchronization.
- **Logos integration** - synchronizes Bible verse navigation with Logos Desktop through local Windows COM automation.
- **Navigation broker** - coordinates Bridge, Paratext, and Logos references while suppressing echoes, duplicate polls, and stale navigation.
- **Production workflow** - includes reviewer roles, assignments, final-approval policy, reports, metrics, Git status/diff/history, and checkpoints.
- **Security and privacy** - protects saved API keys with Windows DPAPI, redacts logs, scans packages for secrets, and exposes AI payload manifests.
- **Reviewer-focused UI** - provides responsive workspaces, scrollable evidence views, keyboard actions, auto-advance, tooltips, and redacted diagnostics.

## Architecture

The application is a Python/Tkinter desktop program. Its source runtime uses only the Python standard library; Windows packaging bundles the interpreter and application into a standalone distribution.

```text
translationCore projects and installed resources
                     |
                     v
        Project adapters and data models
        - project/check/alignment readers
        - language and resource detection
        - deterministic validation
                     |
          +----------+----------+
          |                     |
          v                     v
   Knowledge/evidence       AI preparation
   and local QA             and model routing
          |                     |
          +----------+----------+
                     |
                     v
       Confidence, evidence, and alignment gates
                     |
                     v
             Human review in Tkinter UI
                     |
                     v
      Validated writes, journal, audit, and Git

External navigation:

Paratext <----> Navigation Broker <----> Logos Desktop
                       ^
                       |
                  Bridge UI
```

### Main components

| Area | Modules | Responsibility |
| --- | --- | --- |
| Desktop UI | `tc_ai_bridge/ui.py` | Workspaces, reviewer actions, settings, and background task coordination |
| Project data | `tc_ai_bridge/tc_project.py`, `models.py`, `usfm.py` | translationCore discovery, parsing, validation, and safe writes |
| Alignment | `alignment_engine.py`, `alignment_reliability.py` | Manual alignment, AI link validation, deterministic compilation, and existing-work protection |
| AI | `ai_client.py`, `model_router.py`, `review_policy.py` | OpenAI Responses API calls, structured output, model selection, and false-positive reduction |
| Evidence and QA | `knowledge_base.py`, `local_checks.py`, `analytics.py`, `psalms_qa.py` | Project-aware evidence, deterministic checks, terminology analytics, and candidate QA |
| Language support | `plugins.py`, `text_graphemes.py` | Source/target language detection and language-specific behavior |
| Safety and operations | `transaction_journal.py`, `cache_engine.py`, `security.py`, `git_service.py` | Recovery, stale-result protection, privacy controls, and project checkpoints |
| Integrations | `navigation.py`, `paratext_connector.py`, `paratext_api.py`, `paratext_notes.py`, `logos_connector.py` | Navigation brokering, Paratext notes/connectivity, and Logos Desktop automation |

See [Architecture](docs/ARCHITECTURE.md) for the detailed authority, alignment, connector, and storage design.

## Run locally

### Prerequisites

- Windows 10 or Windows 11
- 64-bit Python 3.11 or 3.12 from [python.org](https://www.python.org/downloads/windows/)
- a translationCore data folder for project-backed workflows
- an OpenAI API key for AI-assisted features
- Git for Windows only if you need checkpoint, history, or diff features

The translationCore data folder supplied to the application should contain `projects` and `resources` directories.

### Windows development setup

Open PowerShell in the repository root and create the local virtual environment:

```powershell
.\setup_windows.bat
```

Run with a console attached so tracebacks and diagnostic output remain visible:

```powershell
.\run_console_windows.bat
```

To load a translationCore data folder at startup:

```powershell
.\run_console_windows.bat --root "C:\path\to\translationCore"
```

You can also invoke the package directly:

```powershell
.\.venv\Scripts\python.exe -m tc_ai_bridge --root "C:\path\to\translationCore"
```

There is no hot-reload development server. Restart the desktop application after changing source code.

For normal source-mode use without a console window:

```powershell
.\run_windows.bat
```

### OpenAI configuration

Enter the API key in **Settings & Log** inside the application. On Windows, the application can persist the key using the current user's DPAPI protection.

For a temporary development session, set the environment variable before launching:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
.\run_console_windows.bat
```

Project browsing and deterministic checks remain available without an API key; AI actions do not.

### Tests

Run the portable Windows regression suite:

```powershell
.\test_windows.bat
```

Press Enter when prompted for a translationCore folder to run only portable tests. To include real-backend certification, pass the data root explicitly:

```powershell
.\test_windows.bat "C:\path\to\translationCore"
```

Real-backend certification creates a disposable project clone. Write-capable tests do not target the live translationCore projects.

For the complete Windows certification process, see [Windows Certification Checklist](docs/WINDOWS_CERTIFICATION_CHECKLIST.md).

## Optional integrations

- [Paratext live connector](docs/PARATEXT_LIVE_CONNECTOR.md)
- [Paratext Notes compatibility](docs/PARATEXT_NOTES_COMPATIBILITY.md)
- [Logos live navigation](docs/LOGOS_LIVE_NAVIGATION.md)

Paratext and Logos integrations are Windows-specific and require separate field certification against the locally installed applications.

## Build a Windows package

Create the standalone application and installer on a Windows build machine:

```powershell
.\build_windows_installer.bat
```

End users should normally receive the generated installer rather than run the source tree. See [Fresh Windows Installation](docs/FRESH_WINDOWS_INSTALL.md) for distribution requirements.


## License

See [LICENSE](LICENSE).
