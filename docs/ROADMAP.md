# Roadmap after v0.7.4

v0.7.4 intentionally focuses on alignment reliability and safe integration foundations. Recommended next milestones should be driven by real chapter-level reviewer use.

## Highest-priority field validation

- Measure duplicate/overlap warnings before vs. after the Alignment Compiler.
- Review compiler `uncertain_links` and protected-group conflicts for false positives.
- Run Existing Work Scan on completed/partial books and confirm no unexpected rewrite.
- Exercise fail → navigate away → return → rerun behavior and confirm stale results never reappear.
- Compare reviewer time for Fill Alignment Gaps vs. older full-verse proposal generation.

## Paratext connector next step

Build the actual companion `.ptxplg` against the official Paratext Plugin API and wire:

- current Paratext user/project/reference;
- `VerseRefChanged` → Bridge navigation;
- Bridge reference → `SetReferenceForSyncGroup`;
- selected Scripture text/context;
- project-note creation on the selected text;
- echo/request IDs to prevent navigation loops.

Keep Scripture writing disabled unless a later, separately reviewed workflow explicitly needs it.

## Identity next step

If a reliable supported translationCore session API/storage location is confirmed, add read-only live signed-in username detection. Until then keep project Git identity clearly labelled.

## Other future enhancements

- code signing / SmartScreen reputation;
- additional language plugins and deeper Greek workflows;
- richer consultant-configurable approval gates;
- multi-machine reviewer directory/authentication;
- deeper Psalms Editor integration;
- optional local/on-prem model backends;
- measured baseline study of manual translationCore review time and Bridge-assisted time.

All future work should preserve: **AI prepares; deterministic software validates; humans decide and approve.**
