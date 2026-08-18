# v0.7.4 Production Readiness Matrix

Status vocabulary: **Implemented** means the capability exists and has automated coverage in this source release. **Windows certification pending** means the build/test workflow exists but the exact compiled Windows artifact must still execute through the Windows checklist.

| # | Production work | v0.7.4 status | Implementation |
|---|---|---|---|
| 1 | Native tC comments/discussion sync | Implemented | Reviewer TN/TW discussion/rejection notes can be appended using observed native `checkData/comments` contextId shape; companion decision/audit remains alongside it. |
| 2 | Windows packaging/certification | Build pipeline implemented; binary certification pending | Icon-bearing PyInstaller one-dir build, Inno Setup installer, Windows 3.11/3.12 CI matrix, certification checklist. |
| 3 | Crash recovery / transaction journal | Implemented | Durable prepared/writing/committed/rollback journal with pre-write backups and conservative startup rollback. |
| 4 | Project Git integration | Implemented | Repository status, diff, history and explicit human checkpoint commits. |
| 5 | Book terminology / TW analytics | Implemented | Concept occurrences, current tC selections, rendering frequencies, human rule classification and unexplained occurrences. |
| 6 | Project exception-first review | Implemented | Cross-chapter priority queue plus changed-book preparation. |
| 7 | Changed-only dependency engine/cache | Implemented | Persistent verse AI cache + component hashes for Scripture, alignment, checks, resources, terminology, manifest, prompt schema and model policy. |
| 8 | Smart model routing/cost | Implemented | Economy/balanced/quality/fixed routing; task/severity escalation; token/cached-token cost estimate; session warning. |
| 9 | KB provenance/version management | Implemented | Project pinning/fallbacks, resource manifests, per-evidence SHA-256 and project/source version provenance. |
| 10 | Psalms structure/parallelism QA | Implemented as conservative candidate QA | Hebrew cantillation-colon clues, lexical repetition, contrast/negation, source compression, unaligned source; human scholarly judgment remains authoritative. |
| 11 | Reporting/publication QA | Implemented | Print-friendly HTML + JSON + QA/exception/terminology CSVs, publication gate, provenance, metrics. |
| 12 | Team/reviewer workflow | Implemented | Roles, assignments, approval policy and role-gated final verse approval. |
| 13 | Security/privacy hardening | Implemented | DPAPI credential persistence on Windows, no plaintext key in settings, log redaction, package secret scan, `store:false`, AI request privacy manifest. |
| 14 | Broader destructive/regression testing | Implemented/continuous | Real backend parsing, transactional rollback, comments sync, UI breakpoints, failure paths, fabricated-token rejection, stale-file guard, synthetic scale fixture. |
| 15 | Production UI redesign | Implemented within Tk shell | Responsive header/sidebar/toolbars, persistent status/progress/tokens/cost, fixed controls outside AI sash, aligned review panes, supplied icon. A future Qt/web shell remains optional—not required for the production data engine. |
| 16 | Full Bible-scale performance | Implemented architecture + synthetic scale test | O(1) materialized verse check lookup; 66-book/~31k-verse synthetic discovery/parse regression; actual supplied 2,722-verse corpus regression. |
| 17 | Plugin/language architecture | Implemented foundation | Tamil target plugin, generic target fallback, Hebrew and Koine Greek source descriptors, registry extension points. |
| 18 | Quality metrics | Implemented | AI prepared checks/findings, cache skips, token/cost totals, human accept/edit/reject/discussion and QA decision metrics. No unsupported claim of time saved is inferred. |

## Production gate that remains external to this Linux build

The exact v0.7.4 EXE/installer must pass `WINDOWS_CERTIFICATION_CHECKLIST.md` on the supported Windows machines. Until that happens, this release is **source/regression certified, Windows packaging-ready**, not a cryptographically signed or Windows-runtime-certified binary.
