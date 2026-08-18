# Paratext Project Notes compatibility — v0.7.4

## What changed

The user-supplied XML uses a `<CommentList>` export/list representation. It was valuable for learning how Paratext preserves selected text, start positions, context, users and comment content, but the supported Paratext Data Access Project Notes endpoint uses a different payload: **Paratext Notes 1.1**.

v0.7.4 therefore separates the two representations:

- `CommentList` — readable/migratable reference and optional interchange/report representation.
- `notes version="1.1"` — primary API-ready Project Notes payload.

## Notes 1.1 structure used by the Bridge

```xml
<notes version="1.1">
  <thread id="generated-thread-id">
    <selection
      verseRef="JOS 3:4"
      startPos="27"
      selectedText="3,000 அடிகள்"
      beforeContext="..."
      afterContext="..." />
    <comment
      user="REAL_PARATEXT_PROJECT_MEMBER"
      date="2026-08-15T09:00:00.0000000+05:30"
      extUser="AI Suggestion">
      <content>ஒரு கிலோமீட்டர்</content>
    </comment>
  </thread>
</notes>
```

## Why `AI Suggestion` is `extUser`

The official Paratext Notes API requires `comment@user` to be a real user on the project. A non-administrator cannot submit a comment on behalf of another project user. The Notes 1.1 schema provides `extUser` specifically for tracking an external user/origin, so the Bridge records AI-originated suggestions as `extUser="AI Suggestion"` while authenticating and writing the comment as the real Paratext project member.

## How a note is attached to text

The Bridge builds the current verse snapshot and attaches the note to an exact contiguous target-language string:

1. exact selected target text, when available;
2. otherwise the longest exact contiguous segment from a reconstructed TN/TW selection;
3. otherwise real verse-level target text for general QA notes.

It never invents a character position for text that is not present.

## How the correct Paratext project is selected

The live destination is **not inferred from a local XML filename**. The local Paratext connector reports the active Paratext project ID and current Paratext user. v0.7.4 stores that project ID mapping independently for each translationCore project. **Verify / Bind Project** now verifies the active local Paratext project through the Plugin API and can bind an unbound translationCore project explicitly.

## Synchronization workflow

```text
Human reviewer decision
        ↓
Bridge Notes 1.1 companion
        ↓
Verify active local Paratext project + user
        ↓
Human chooses Sync Notes to Paratext
        ↓
Named pipe → Paratext Plugin API
        ↓
ProjectNotes write lock → IProject.AddNote(...)
        ↓
Paratext records the current logged-in user as the real note author
```

The Bridge does not call a Scripture-write API during Project Notes synchronization. The older Data Access client is retained only as an advanced/legacy implementation path; the Production/Settings Verify and Sync buttons use the local connector.

## Migration

v0.7.1 `<CommentList>` companion files and earlier Bridge Notes 1.1 files are preserved. Where necessary, v0.7.1 CommentList records are migrated into the corrected Notes 1.1 companion without deleting the historical source file.

The supplied 785-comment XML sample has been parsed successfully by the compatibility validator, and conversion generated 785 valid Bridge Notes 1.1 threads in the local regression check.

## Live certification boundary

Schema/structure, selection offsets, project binding, author normalization, local batch-sync bookkeeping and connector request construction are automated-test covered. Real Project Note creation still requires Windows field certification against the user's installed Paratext 9.5.110.1 and its actual project permissions.

## v0.7.4 local Plugin API connector foundation

Paratext Notes 1.1 remains the Bridge companion/export representation. The **local Plugin API connector is now the primary live synchronization path** for Verify Project and Sync Notes. Data Access code is retained only for advanced/legacy use.

The connector uses a Windows named pipe (`\\.\pipe\translationCoreAIBridge`) and a small JSON-line protocol. The Paratext startup plugin exposes current user/project/reference/selection and accepts only safe actions such as setting the current reference or creating a Project Note. The Bridge contains no Scripture-write command.

A precompiled `.ptxplg` is not shipped because the connector is compiled on the user's Windows machine against the installed Paratext Plugin API assemblies. The included installer/build scripts produce and install `translationCoreAIBridge.ptxplg`.
