# Translation Helps Knowledge Base Audit

Backend analyzed: user-supplied translationCore backend, tC data version 8 / edit version 3.7.0.

## Installed Translation Helps generations

| Resource | Installed generations/copies |
|---|---|
| Translation Academy | v85 Door43, v85 unfoldingWord, v87 Door43, v87 unfoldingWord |
| Translation Notes | v85.2 Door43, v85.2 unfoldingWord, v87 Door43, v87 unfoldingWord |
| Translation Words | v85 Door43, v85 unfoldingWord, v87 Door43, v87 unfoldingWord |
| Translation Words Links | v85.1 unfoldingWord, v87 unfoldingWord |

Ruth and Obadiah manifests explicitly pin TN/TW to `v87_unfoldingWord`. Psalms has no TN/TW pin in its manifest, so the resolver selects latest compatible installed v87 unfoldingWord resources.

## v87 resource counts

- Translation Academy: 241 Markdown articles.
- Translation Notes: 62,315 occurrence records in 2,528 group/book JSON files; 101 TN group IDs.
- Translation Words: 953 articles.
- Translation Words Links: 62,365 occurrences:
  - key terms 25,809
  - names 11,369
  - other 25,187

## Project check coverage

- Ruth: 559 indexed TN/TW checks.
- Obadiah: 245 indexed TN/TW checks.
- Psalms: 4,583 indexed TW checks.
- Total: 5,387.

Automated audit result: **all 5,387 checks resolve primary knowledge evidence** under the v0.6.5 resolver rules.

For every indexed Translation Note, the resolver supplies the note itself and a Translation Academy article. For every indexed Translation Word, it supplies one or more Translation Word articles.

## Known legacy identifiers handled

- `writing-quotation` resolves to current `writing-quotations`.
- `grammar-honorifics` can fall back to the retained older TA article when needed.
- project TW IDs such as `call` and `generation` can resolve to the relevant current sense-specific article candidates rather than being treated as missing.

All fallbacks are surfaced in provenance rather than silently disguised as current exact matches.
