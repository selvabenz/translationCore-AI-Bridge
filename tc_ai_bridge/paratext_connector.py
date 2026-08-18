from __future__ import annotations

import ctypes
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

PIPE_NAME = r'\\.\pipe\translationCoreAIBridge'
PROTOCOL_VERSION = 1


class ParatextConnectorError(RuntimeError):
    pass


@dataclass
class ConnectorState:
    connected: bool = False
    user: str = ''
    project_name: str = ''
    project_id: str = ''
    reference: str = ''
    selected_text: str = ''
    sync_group: str = ''
    project_language: str = ''
    selection_reference: str = ''
    before_context: str = ''
    after_context: str = ''
    selection_offset: int = -1
    paratext_version: str = ''
    plugin_version: str = ''
    state_revision: int = 0
    last_event: str = ''
    last_origin_id: str = ''
    capabilities: list[str] = field(default_factory=list)
    error: str = ''

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> 'ConnectorState':
        return cls(
            connected=bool(data.get('ok', False)),
            user=str(data.get('user', '') or ''),
            project_name=str(data.get('project_name', '') or ''),
            project_id=str(data.get('project_id', '') or ''),
            reference=str(data.get('reference', '') or ''),
            selected_text=str(data.get('selected_text', '') or ''),
            sync_group=str(data.get('sync_group', '') or ''),
            project_language=str(data.get('project_language', '') or ''),
            selection_reference=str(data.get('selection_reference', '') or ''),
            before_context=str(data.get('before_context', '') or ''),
            after_context=str(data.get('after_context', '') or ''),
            selection_offset=int(data.get('selection_offset', -1) if data.get('selection_offset') is not None else -1),
            paratext_version=str(data.get('paratext_version', '') or ''),
            plugin_version=str(data.get('plugin_version', '') or ''),
            state_revision=int(data.get('state_revision', 0) or 0),
            last_event=str(data.get('last_event', '') or ''),
            last_origin_id=str(data.get('last_origin_id', '') or ''),
            capabilities=[str(x) for x in data.get('capabilities', [])] if isinstance(data.get('capabilities'), list) else [],
            error=str(data.get('error', '') or ''),
        )


class ParatextConnectorClient:
    """Small newline-delimited JSON client for the local Paratext companion plugin.

    The companion is optional. On Windows it is expected to host a NamedPipeServerStream at the
    documented pipe name. No network listener or Paratext server credential is required.
    """
    def __init__(self, pipe_name: str = PIPE_NAME, timeout_ms: int = 1200):
        self.pipe_name = pipe_name
        self.timeout_ms = timeout_ms

    def _exchange(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if os.name != 'nt':
            raise ParatextConnectorError('Paratext local connector is available only on Windows.')
        message = {
            'protocol': PROTOCOL_VERSION,
            'id': uuid.uuid4().hex,
            'action': action,
            'payload': payload or {},
        }
        try:
            # Fail quickly when the companion is not available/busy; do not let the Tk UI hang on
            # a named-pipe open. WaitNamedPipeW is Windows-local and uses milliseconds.
            if not ctypes.windll.kernel32.WaitNamedPipeW(self.pipe_name, int(self.timeout_ms)):
                raise ParatextConnectorError('Paratext AI Bridge Connector is not available within the connection timeout.')
            # Windows named pipes can then be opened like files. The companion closes each response
            # with a newline, keeping the protocol implementation-neutral.
            with open(self.pipe_name, 'r+b', buffering=0) as pipe:
                pipe.write((json.dumps(message, ensure_ascii=False) + '\n').encode('utf-8'))
                chunks = bytearray()
                while True:
                    b = pipe.read(1)
                    if not b or b == b'\n':
                        break
                    chunks.extend(b)
                    if len(chunks) > 2_000_000:
                        raise ParatextConnectorError('Paratext connector response exceeded safety limit.')
        except FileNotFoundError as exc:
            raise ParatextConnectorError('Paratext AI Bridge Connector is not running/installed.') from exc
        except OSError as exc:
            raise ParatextConnectorError(f'Could not communicate with Paratext connector: {exc}') from exc
        try:
            data = json.loads(chunks.decode('utf-8')) if chunks else {}
        except Exception as exc:
            raise ParatextConnectorError('Paratext connector returned invalid JSON.') from exc
        if not isinstance(data, dict):
            raise ParatextConnectorError('Paratext connector returned an unexpected response.')
        if data.get('id') not in (None, message['id']):
            raise ParatextConnectorError('Paratext connector response/request ID mismatch.')
        if data.get('ok') is False:
            raise ParatextConnectorError(str(data.get('error') or 'Paratext connector operation failed.'))
        return data

    def get_state(self) -> ConnectorState:
        return ConnectorState.from_response(self._exchange('get_state'))

    def set_reference(self, reference: str, origin_id: str = '') -> dict[str, Any]:
        return self._exchange('set_reference', {'reference': reference, 'origin_id': origin_id or uuid.uuid4().hex})

    def create_note(
        self,
        reference: str,
        selected_text: str,
        comment: str,
        assignee: str = '',
        *,
        project_id: str = '',
        before_context: str = '',
        after_context: str = '',
    ) -> dict[str, Any]:
        return self._exchange('create_note', {
            'reference': reference,
            'selected_text': selected_text,
            'comment': comment,
            'assignee': assignee,
            'project_id': project_id,
            'before_context': before_context,
            'after_context': after_context,
            'external_author': 'AI Suggestion',
        })
