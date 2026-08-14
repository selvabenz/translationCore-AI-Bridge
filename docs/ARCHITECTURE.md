# Architecture — v0.7.0

```text
translationCore project
 ├─ target chapter JSON / manifest / Git
 ├─ alignmentData / WA completion-invalid state
 ├─ checkData / indexes / comments / verse edits
 └─ installed Translation Helps + original language
             │
             ▼
      Project / KB adapters
             │
       language detector
        + plugin policy
             │
 ┌───────────┼──────────────────────────────────────┐
 │           │                                      │
 ▼           ▼                                      ▼
Dependency  Deterministic QA                   Knowledge graph
cache       / validators                       TN→TA, TW→TWL,
 │                                                morphology,
 │                                                provenance
 └───────────────┬──────────────────────────────────┘
                 ▼
          Model router / OpenAI
                 │
        structured AI proposals
                 │
        confidence/evidence gate
                 │
                 ▼
            HUMAN REVIEW
       Accept/Edit/Discuss/Reject
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
 tC project writers     Paratext Notes
 + transaction safety   1.1 exchange XML
       │
       ▼
 stale propagation + Git checkpoint + audit/metrics
```


## Production subsystems

- `transaction_journal.py` — durable crash recovery and rollback.
- `git_service.py` — project status, diff, history, human checkpoint.
- `analytics.py` — TW terminology and exception-first project queue.
- `cache_engine.py` — component dependency hashes/stale reasons.
- `model_router.py` — economy/balanced/quality/fixed model policy and cost estimate.
- `metrics.py` — observed workflow/quality/cost metrics.
- `security.py` — log redaction, package secret scan and privacy manifest.
- `team.py` — reviewer roles, assignments and final-approval policy.
- `plugins.py` — project-detected source/target language context, UI/prompt/QA extension points.
- `review_policy.py` — confidence/evidence/duplicate gate that reduces AI false positives before human review.
- `paratext_notes.py` — Paratext Notes 1.1-compatible reviewer-note exchange XML.
- `psalms_qa.py` — specialized candidate structural/parallelism QA.
- `reporting.py` — deterministic publication QA exports.

## Write rule

AI is never a project writer. A project write that represents a translation/checking decision is reachable only through a human action. Multi-file tC writes are protected by validation, backups and the transaction journal.
