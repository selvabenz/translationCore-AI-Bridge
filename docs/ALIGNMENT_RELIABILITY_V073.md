# v0.7.4 Alignment Reliability Design

## Problem addressed

Earlier alignment AI responses were asked to emit final translationCore groups. A linguistically valid many-to-one relationship could be emitted as two overlapping groups, for example `H008→T014` and `H009→T014`. The strict validator then rejected the repeated target token. Leaving and returning to the verse cleared transient proposal state and a new AI request could happen to format the same relationship differently, explaining intermittent success.

v0.7.4 treats that behavior as an architectural issue rather than weakening validation.

## New contract

AI returns individual linguistic edges:

```json
{
  "links": [
    {"top_id":"H008","bottom_id":"T014","confidence":0.94,"reason":"..."},
    {"top_id":"H009","bottom_id":"T014","confidence":0.89,"reason":"..."}
  ],
  "implicit_top_ids": [],
  "target_only_ids": [],
  "review_notes": []
}
```

The deterministic compiler owns final group construction.

## Deterministic rules

- Validate IDs against the exact current verse inventory.
- Deduplicate identical edges.
- Strong edges (`>=0.72`) participate in connected components.
- Medium edges (`>=0.45` and `<0.72`) are visible for review but cannot join components.
- Low edges are recorded and ignored for automatic grouping.
- Final group confidence is conservatively the minimum confidence among the component's compiled edges.
- Token order/adjacency is not required for group membership.
- The final proposal still passes the legacy structural validator.

## Existing work

In gap-fill mode, established non-empty project groups are protected. Human-approved verses use a hard lock. Historical/partial groups can be extended only when an unresolved endpoint needs to attach to one established group; the extension is still merely an in-memory proposal until the reviewer explicitly applies and saves it. A link/component that would join two established groups is rejected as a conflict.

## Source/target asymmetry

`implicit_top_ids` handles source meaning represented without a separate target token. `target_only_ids` handles legitimate target-language grammatical/natural material with no separate source token. Target-only candidates stay in wordBank and are explicitly reviewable; the compiler never invents a source relationship just to achieve 100% target coverage.

## Asynchronous safety

A response can be used only if the current state still matches its immutable request context:

- project path;
- book/chapter/verse;
- source fingerprint;
- target text/token fingerprint;
- alignment fingerprint;
- request ID provenance.

Navigation or edits during AI work invalidate the response. Starting a new request also clears the previous pending alignment proposal immediately.

## Compatibility principle

The new engine migrates the Bridge's understanding of old work, not the old alignment itself. Existing finished work is protected and audited exception-first. No book-wide automatic rewrite is performed.
