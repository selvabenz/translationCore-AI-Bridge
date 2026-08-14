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

# Production settings are deliberately simple JSON values; secrets remain DPAPI-protected above.
def _get_setting(self, key, default=None):
    return self.data.get(key, default)
def _set_setting(self, key, value):
    self.data[key]=value; self.save_sanitized()
AppSettings.get_setting=_get_setting
AppSettings.set_setting=_set_setting
