# Local Connector Protocol v1

Transport: Windows named pipe only.

```text
\\.\pipe\translationCoreAIBridge
```

Encoding: UTF-8, one JSON request and one JSON response per pipe connection, newline terminated.

## Request envelope

```json
{"protocol":1,"id":"request-id","action":"get_state","payload":{}}
```

## Supported actions

### `get_state`

Returns current Paratext state:

```json
{
  "ok": true,
  "user": "Reviewer",
  "project_name": "Tamil IRV",
  "project_id": "paratext-project-id",
  "project_language": "Tamil",
  "reference": "GEN 1:1",
  "selected_text": "ஆதியிலே",
  "selection_reference": "GEN 1:1",
  "before_context": "",
  "after_context": " தேவன்...",
  "selection_offset": 0,
  "sync_group": "A",
  "paratext_version": "9.5.110.1",
  "plugin_version": "0.7.4",
  "state_revision": 12,
  "last_event": "selection_changed",
  "last_origin_id": "",
  "capabilities": ["state","navigation","selection","project_notes"]
}
```

### `set_reference`

```json
{"protocol":1,"id":"...","action":"set_reference","payload":{"reference":"GEN 1:2","origin_id":"..."}}
```

The connector asks Paratext's own project versification to parse the standard reference and uses the active window's existing scroll/sync group. It fails if the window is not in a sync group.

### `create_note`

```json
{
  "protocol":1,
  "id":"...",
  "action":"create_note",
  "payload":{
    "project_id":"...",
    "reference":"GEN 1:1",
    "selected_text":"ஆதியிலே",
    "before_context":"",
    "after_context":" தேவன்...",
    "comment":"Review this rendering.",
    "assignee":"",
    "external_author":"AI Suggestion"
  }
}
```

Safety behavior:

- verifies the active Paratext project ID when supplied;
- uses the active exact Scripture selection when it matches;
- otherwise finds matching Scripture selections through the Plugin API;
- unique match is allowed;
- multiple unresolved matches are rejected;
- empty selected text creates a verse-level Project Note anchor;
- obtains a `ProjectNotes` write lock;
- creates a Project Note only.

## Deliberately unsupported

There is no protocol action for:

```text
PutUSFM
PutUSFMTokens
PutUSX
Scripture editing
Project settings changes
Silent note deletion/resolution
```

The Python Bridge rejects unknown actions because the C# adapter has an explicit allow-list.
