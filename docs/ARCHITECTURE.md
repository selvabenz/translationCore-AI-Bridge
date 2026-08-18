# Architecture — translationCore AI Bridge v0.7.5

## v0.7.5 navigation layer

The Bridge now owns a small deterministic `NavigationBroker` above the Paratext and Logos adapters. External applications never forward directly to one another. Accepted references enter the Bridge, are normalized/validated against loaded projects, and are forwarded only to the other enabled connector(s). Recent outbound echoes and unchanged polled state are ignored.

Logos is connected on Windows through a hidden persistent PowerShell STA helper and the locally registered `LogosBibleSoftware.Launcher` COM component. Continuous Logos COM polling/navigation does not run on the Tk main thread; rapid outbound navigation is coalesced so the latest target wins. No Logos credentials or network listener are introduced. See `LOGOS_LIVE_NAVIGATION.md`.


## Authority model

The application preserves a strict boundary:

```text
Project + installed resources
          ↓ read
Deterministic resolvers / validators
          ↓
AI preparation and evidence
          ↓
Bridge proposal workspace
          ↓
Human review / decision
          ↓
Approved translationCore-compatible writes
```

AI never silently rewrites Scripture, approves alignment, completes TN/TW, changes terminology or grants final verse/project approval.

## v0.7.4 alignment architecture

The important change is separation of linguistic inference from file-structure construction.

```text
Source + target token inventory
            ↓
Existing alignment/provenance
            ↓
     lock classification
            ↓
AI: individual linguistic links
            ↓
Deterministic Alignment Compiler
            ↓
translationCore structural validator
            ↓
Human Apply / Edit / Reject
            ↓
Safe transaction + approved project data
```

### AI layer

The model sees the complete verse as context and receives explicit unresolved IDs. It may return:

- source↔target links with per-edge confidence/reason;
- `implicit_top_ids` when a source element has no separate target token;
- `target_only_ids` when legitimate target-language grammatical/natural material has no separate source token;
- reviewer notes.

The model does **not** determine the final translationCore group topology.

### Compiler layer

`tc_ai_bridge/alignment_reliability.py`:

- validates every token ID against the current verse inventory;
- deduplicates identical links;
- divides links into strong / uncertain / low-confidence bands;
- computes connected components from strong edges only;
- emits deterministic 1→1, 1→many, many→1 and many→many groups;
- does not assume token adjacency, so discontinuous phrase groups remain possible;
- blocks components that connect two established protected groups;
- blocks any extension of a human-approved hard lock;
- may prepare a legacy/partial protected-group extension only as an unsaved human-review proposal;
- keeps target-only candidates in wordBank for explicit review;
- records normalization/conflict diagnostics.

The final `validate_proposal()` still rejects illegal membership, fabricated IDs and duplicate final token membership.

## Existing-work policy

`TranslationCoreProject.alignment_lock_state()` classifies a verse:

- `HARD_LOCK`: explicit Bridge human approval.
- `PROTECTED_LEGACY`: completed existing alignment without sufficient Bridge provenance.
- `PARTIAL_PROTECTED`: useful existing groups plus unresolved work.
- `OPEN`: no established alignment.

This classification changes what AI is allowed to propose; it does not rewrite old data.

`alignment_compatibility_scan()` is read-only. `ensure_v073_migration_snapshot()` records hashes/byte sizes of alignment chapter files under Bridge companion data. The migration snapshot is provenance, not a replacement alignment dataset.

## Verse-bound asynchronous AI

Temporary aliases such as `H014` and `T014` are scoped to the loaded verse. They are not persistent identity.

Each asynchronous alignment request therefore carries:

- unique request ID;
- project path + book;
- chapter + verse;
- source-token fingerprint;
- target verse/token fingerprint;
- alignment fingerprint.

When the result returns, all fingerprints are recomputed. Any mismatch discards the stale result. This protects navigation, Scripture edits, alignment edits and project switches that occur while AI is running.

Persistent token comparison continues to rely on actual token signatures/occurrence metadata rather than transient aliases.

## Knowledge/evidence architecture

Evidence priority remains:

1. project data and human-approved decisions;
2. project-pinned original-language/source resources;
3. project-pinned Translation Notes / Words / Links / Academy;
4. established project terminology/reviewer history;
5. secondary reference Bible;
6. AI inference.

English reference text never outranks the Hebrew/Greek source.

## Language/plugin architecture

Project target language is derived from manifest metadata plus script evidence; source language from source tokens/canon. Plugins affect:

- language names/labels;
- fonts;
- target-language QA guidance;
- AI prompt context;
- script/direction behavior.

Plugins do not silently reinterpret persisted alignment data.

## Door43 identity

`tc_ai_bridge/identity.py` reads project `.git/config` only. It may derive a Door43 username from a Door43 noreply email and expose Git name/email/remote owner. This is project repository identity, not proof of a live translationCore authentication session. No password/token is read or persisted.

## Paratext architecture

Two integrations are intentionally separate.

### Data Access / Notes 1.1

Existing production path:

```text
Bridge reviewer note
      ↓
Paratext Notes 1.1 XML
      ↓ explicit user action
Authenticated Data Access POST
      ↓
Configured Paratext project GUID
```

Scripture text is not POSTed by note synchronization.

### Local Plugin API connector foundation

v0.7.4 adds:

```text
Python Bridge
    │ local Windows named pipe
    ▼
C# connector transport
    │ future Paratext Plugin API adapter
    ▼
Paratext
```

Protocol foundation supports state/reference/note concepts. The intended safe adapter can read current user/project/reference/selection, synchronize verse navigation and create selected-text notes. There is no automatic Scripture-write command. A compiled `.ptxplg` is not part of v0.7.4.

## Storage/write boundaries

Read-only by default:

- Scripture/resources/source helps;
- compatibility scan;
- alignment audit;
- compiler diagnostics.

Explicit human-authorized writes include:

- approved alignment;
- approved TN/TW state;
- human Scripture correction;
- terminology decisions;
- reviewer decisions/comments;
- Bridge companion audit/recovery/metrics data.

Multi-file writes use transaction/rollback protection where appropriate.

## v0.7.4 — Paratext Live Connector

The local integration boundary is now:

```text
Bridge Python process
  └─ ParatextConnectorClient
      └─ Windows named pipe \\.\pipe\translationCoreAIBridge
          └─ Paratext startup plugin (.ptxplg)
              └─ official Plugin API
```

The plugin's protocol is allow-listed to `get_state`, `set_reference`, and `create_note`. Project Notes are the only Paratext write scope. Scripture-writing APIs are deliberately absent. Every live write also requires the current translationCore project's stored Paratext project ID to match the project currently active in Paratext.

The existing Paratext Notes 1.1/Data Access integration remains a separate explicit server/export path and can be used when the local plugin is unavailable.
