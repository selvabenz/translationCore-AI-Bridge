# Paratext Live Connector — v0.7.4

## Purpose

The Live Connector lets translationCore AI Bridge cooperate with a running Paratext 9.5 instance on the same Windows computer without scraping Paratext files or opening a network service.

Targeted first field environment: **Paratext 9.5.110.1**.

## Architecture

```text
translationCore AI Bridge
Python / Tkinter
        │
        │ \\.\pipe\translationCoreAIBridge
        │ UTF-8 JSON, local Windows pipe
        ▼
translationCore AI Bridge Connector
Paratext .ptxplg / C#
        │
        ▼
Paratext Plugin API
        │
        ▼
Paratext 9.5
```

The companion implements the automatic startup plugin interface so it is available after Paratext starts.

## Capabilities

### Read state

- Paratext user name;
- active project short name;
- active project ID;
- project language;
- current Scripture reference;
- current scroll/sync group;
- active Scripture selection;
- before/after selection context;
- Paratext/plugin versions.

### Navigation

The Bridge uses Paratext's current project's versification to parse a standard Scripture reference, then sets the reference of the **existing active scroll/sync group**. It never silently chooses a sync group.

Paratext reference-change events are exposed back to the Bridge. An origin ID prevents ordinary Bridge-originated navigation from bouncing back repeatedly.

### Project Notes

The plugin can create Project Notes only. It:

1. verifies the expected Paratext project ID;
2. resolves the verse through Paratext's own versification;
3. prefers the active exact Scripture selection;
4. otherwise searches for matching Scripture selections;
5. refuses unresolved duplicate occurrences;
6. uses a verse-level selection if selected text is empty;
7. requests a `ProjectNotes` write lock;
8. calls the Project Notes API.

The actual note author is the current Paratext user. AI-originated content is identified in the content as `[AI Suggestion]` rather than inventing a Paratext member identity.

`Notes_AI_Suggestion.xml` is only the Bridge companion/export filename. It is **not** used as a Paratext username. When an API-ready XML copy is exported, `comment@user` is normalized to the detected/configured real Paratext user and `extUser="AI Suggestion"` preserves AI provenance.

## Project binding

The live connection has a separate safety mapping:

```text
translationCore project  ──bound to──>  Paratext project ID
```

A live note or synchronized navigation is blocked when the active Paratext project differs from the stored binding.

This is intentionally per translationCore project. Multiple translationCore book projects may be explicitly bound to the same whole-Bible Paratext project ID.

## Write boundary

Allowed write:

```text
Paratext Project Notes
```

Not implemented:

```text
PutUSFM
PutUSFMTokens
PutUSX
Scripture editing
Project-settings editing
Silent note deletion/resolution
```

The existing Bridge Scripture correction workflow remains separate and human-controlled.

## Build/install boundary

The source package does not claim a precompiled `.ptxplg` binary has been certified. The Windows install script compiles the plugin against the PluginInterfaces assembly found in the user's installed Paratext. This compilation/loading step must be certified on the actual Windows/Paratext installation.

See `../paratext_connector/INSTALL_WINDOWS.md`.
