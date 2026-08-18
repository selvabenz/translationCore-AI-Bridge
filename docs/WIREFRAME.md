# v0.7.4 Responsive Runtime UI Map

The old screenshot-like title banner has been removed. The OS window title and supplied app icon identify the application without consuming workspace height.

```text
┌ [icon] translationCore folder [path.........] [Load]  [● API] ┐
│ Project [........]  Ch[..] V[..]                               │
├───────────────┬─────────────────────────────────────────────────┤
│ Dashboard     │ active workspace                                │
│ Alignment     │                                                 │
│ AI Final      │                                                 │
│ Quality       │                                                 │
│ tC State      │                                                 │
│ KB            │                                                 │
│ Terminology   │                                                 │
│ Psalms QA     │                                                 │
│ Production    │                                                 │
│ Settings      │                                                 │
├───────────────┴─────────────────────────────────────────────────┤
│ Status………………… [========== progress ==========] Tokens  Cost    │
└──────────────────────────────────────────────────────────────────┘
```

At narrower widths the sidebar and explanatory header labels collapse, while project/navigation, API light, status/progress/tokens/cost remain accessible.

## Alignment

```text
Tamil verse
[Connect] [Unalign] [Undo] [Redo] [AI Suggest] ... [Groups…]
──────────────────────────────────────────────────────────────
Hebrew topWords | Tamil bottomWords | Current groups (wide)
══════════════════ draggable sash ════════════════════════════
AI Proposal (resizable)
```

The action toolbar is not a child of the draggable pane, so sash movement cannot hide it. Compact widths hide the derived Groups pane and expose it with **Groups…**.

## AI Final Review

```text
[AI Full Verse] [Changed Chapter] [Full Audit]
Critical | High | Medium | Editorial | Info
──────────────────────────────────────────────────────────────
Severity + Tool Viewer    | Result + Evidence
──────────────────────────────────────────────────────────────
[Accept] [Edit Selection] [Needs Discussion] [Reject] [Edit Scripture]
```

The viewers share one aligned Panedwindow; human decision controls remain outside it.
