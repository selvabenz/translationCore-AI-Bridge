from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path


class SecretStoreError(RuntimeError):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def dpapi_protect(text: str) -> str:
    if os.name != 'nt':
        raise SecretStoreError('Windows DPAPI is only available on Windows.')
    data, keep = _blob(text.encode('utf-8'))
    out = DATA_BLOB()
    # CRYPTPROTECT_UI_FORBIDDEN = 1
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(data), 'translationCore AI Bridge', None, None, None, 1, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        raw = ctypes.string_at(out.pbData, out.cbData)
        return base64.b64encode(raw).decode('ascii')
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def dpapi_unprotect(encoded: str) -> str:
    if os.name != 'nt':
        raise SecretStoreError('Windows DPAPI is only available on Windows.')
    raw = base64.b64decode(encoded)
    data, keep = _blob(raw)
    out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(data), None, None, None, None, 1, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode('utf-8')
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


class AppSettings:
    def __init__(self, path: Path | None = None):
        if path is None:
            root = Path(os.getenv('LOCALAPPDATA') or Path.home() / '.translationcore-ai-bridge')
            path = root / 'settings.json'
        self.path = Path(path)
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text('utf-8'))
            except Exception:
                self.data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding='utf-8')

    def set_api_key(self, key: str, persist: bool = True) -> None:
        self.data.pop('api_key_dpapi', None)
        self.data['_session_api_key'] = key.strip()
        if persist and key.strip() and os.name == 'nt':
            self.data['api_key_dpapi'] = dpapi_protect(key.strip())
        self.save_sanitized()

    def save_sanitized(self) -> None:
        persistent = {k: v for k, v in self.data.items() if not k.startswith('_')}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(persistent, indent=2), encoding='utf-8')
        # The persisted file never contains a plaintext API key. Restrict other reviewer/settings
        # metadata as well on platforms that support POSIX permissions; Windows DPAPI protects
        # the credential material itself.
        try:
            os.chmod(self.path, 0o600)
        except (OSError, NotImplementedError):
            pass

    def get_api_key(self) -> str:
        env = os.getenv('OPENAI_API_KEY', '').strip()
        if env:
            return env
        session = str(self.data.get('_session_api_key', '')).strip()
        if session:
            return session
        enc = str(self.data.get('api_key_dpapi', '')).strip()
        if enc and os.name == 'nt':
            try: return dpapi_unprotect(enc)
            except Exception: return ''
        return ''

    @property
    def model(self) -> str:
        return str(self.data.get('model') or 'gpt-5.6')

    @model.setter
    def model(self, value: str) -> None:
        self.data['model'] = value.strip() or 'gpt-5.6'
        self.save_sanitized()

    @property
    def reviewer_name(self) -> str:
        return str(self.data.get('reviewer_name') or 'AI Bridge Reviewer')

    @reviewer_name.setter
    def reviewer_name(self, value: str) -> None:
        self.data['reviewer_name'] = value.strip() or 'AI Bridge Reviewer'
        self.save_sanitized()

    @property
    def paratext_username(self) -> str:
        return str(self.data.get('paratext_username') or '')

    @paratext_username.setter
    def paratext_username(self, value: str) -> None:
        self.data['paratext_username'] = str(value or '').strip()
        self.save_sanitized()

    @property
    def paratext_project_guid(self) -> str:
        """Legacy/global Paratext GUID fallback.

        v0.7.4 stores GUIDs per translationCore project so switching projects cannot silently
        send notes to the previously selected Paratext project. This property is retained for
        migration and callers that do not yet supply a project key.
        """
        return str(self.data.get('paratext_project_guid') or '')

    @paratext_project_guid.setter
    def paratext_project_guid(self, value: str) -> None:
        self.data['paratext_project_guid'] = str(value or '').strip()
        self.save_sanitized()

    def get_paratext_project_guid(self, project_key: str = '') -> str:
        key = str(project_key or '').strip()
        mapping = self.data.get('paratext_project_guids')
        if key and isinstance(mapping, dict):
            value = str(mapping.get(key) or '').strip()
            if value:
                return value
        return self.paratext_project_guid if not key else ''

    def set_paratext_project_guid(self, project_key: str, value: str) -> None:
        key = str(project_key or '').strip()
        if not key:
            self.paratext_project_guid = value
            return
        mapping = self.data.get('paratext_project_guids')
        if not isinstance(mapping, dict):
            mapping = {}
        else:
            mapping = dict(mapping)
        clean = str(value or '').strip()
        if clean:
            mapping[key] = clean
        else:
            mapping.pop(key, None)
        self.data['paratext_project_guids'] = mapping
        self.save_sanitized()

    def set_paratext_registration_code(self, code: str, persist: bool = True) -> None:
        self.data.pop('paratext_registration_code_dpapi', None)
        self.data['_session_paratext_registration_code'] = str(code or '').strip()
        if persist and str(code or '').strip() and os.name == 'nt':
            self.data['paratext_registration_code_dpapi'] = dpapi_protect(str(code).strip())
        self.save_sanitized()

    def get_paratext_registration_code(self) -> str:
        session = str(self.data.get('_session_paratext_registration_code', '')).strip()
        if session:
            return session
        enc = str(self.data.get('paratext_registration_code_dpapi', '')).strip()
        if enc and os.name == 'nt':
            try:
                return dpapi_unprotect(enc)
            except Exception:
                return ''
        return ''

    def record_ai_usage(self, total_tokens: int = 0, estimated_cost_usd: float = 0.0) -> None:
        """Persist Bridge-observed lifetime API usage for this Windows user/settings file."""
        usage = self.data.get('ai_usage_totals')
        if not isinstance(usage, dict):
            usage = {}
        usage = dict(usage)
        usage['tokens'] = int(usage.get('tokens', 0) or 0) + max(0, int(total_tokens or 0))
        usage['estimatedCostUSD'] = float(usage.get('estimatedCostUSD', 0.0) or 0.0) + max(0.0, float(estimated_cost_usd or 0.0))
        self.data['ai_usage_totals'] = usage
        self.save_sanitized()

    def get_ai_usage_totals(self) -> dict:
        usage = self.data.get('ai_usage_totals')
        if not isinstance(usage, dict):
            return {'tokens': 0, 'estimatedCostUSD': 0.0}
        return {
            'tokens': max(0, int(usage.get('tokens', 0) or 0)),
            'estimatedCostUSD': max(0.0, float(usage.get('estimatedCostUSD', 0.0) or 0.0)),
        }

# Production settings are deliberately simple JSON values; secrets remain DPAPI-protected above.
def _get_setting(self, key, default=None):
    return self.data.get(key, default)
def _set_setting(self, key, value):
    self.data[key]=value; self.save_sanitized()
AppSettings.get_setting=_get_setting
AppSettings.set_setting=_set_setting
