from __future__ import annotations

"""Minimal Paratext Data Access client for explicit Project Notes synchronization.

No background or silent synchronization occurs. The UI calls this only after the reviewer chooses
"Sync Notes to Paratext". Credentials are supplied by AppSettings; registration codes should be
DPAPI-protected on Windows.
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


class ParatextAPIError(RuntimeError):
    pass


class ParatextDataAccessClient:
    def __init__(
        self,
        username: str,
        registration_code: str,
        *,
        registry_token_url: str = 'https://registry.paratext.org/api8/token/',
        data_access_base: str = 'https://data-access.paratext.org',
        timeout: int = 30,
    ):
        self.username = str(username or '').strip()
        self.registration_code = str(registration_code or '').strip()
        self.registry_token_url = registry_token_url.rstrip('/') + '/'
        self.data_access_base = data_access_base.rstrip('/')
        self.timeout = int(timeout)
        self._token = ''
        if not self.username or not self.registration_code:
            raise ParatextAPIError('Paratext username and registration code are required.')

    def _request(self, req: urllib.request.Request) -> bytes:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            try: detail = e.read().decode('utf-8', 'replace')
            except Exception: detail = ''
            raise ParatextAPIError(f'Paratext HTTP {e.code}: {detail or e.reason}') from e
        except urllib.error.URLError as e:
            raise ParatextAPIError(f'Paratext connection failed: {e.reason}') from e

    def acquire_token(self) -> str:
        if self._token:
            return self._token
        basic = base64.b64encode(f'{self.username}:{self.registration_code}'.encode('utf-8')).decode('ascii')
        req = urllib.request.Request(
            self.registry_token_url,
            data=b'',
            method='POST',
            headers={'Authorization': f'Basic {basic}', 'Content-Type': 'application/json', 'Accept': 'application/json'},
        )
        raw = self._request(req)
        try:
            token = str(json.loads(raw.decode('utf-8')).get('access_token') or '').strip()
        except Exception as e:
            raise ParatextAPIError('Paratext Registry returned an unreadable token response.') from e
        if not token:
            raise ParatextAPIError('Paratext Registry response did not contain an access_token.')
        self._token = token
        return token

    def list_projects(self) -> list[dict[str, str]]:
        """Return Paratext projects in which the authenticated user is a member."""
        token = self.acquire_token()
        req = urllib.request.Request(
            f'{self.data_access_base}/api8/projects',
            method='GET',
            headers={'Authorization': f'Bearer {token}', 'Accept': 'application/xml'},
        )
        raw = self._request(req)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            raise ParatextAPIError('Paratext returned unreadable project membership XML.') from e
        out: list[dict[str, str]] = []
        for repo in root.findall('.//repo'):
            out.append({
                'short_name': str(repo.findtext('proj') or '').strip(),
                'guid': str(repo.findtext('projid') or '').strip(),
                'project_type': str(repo.findtext('projecttype') or '').strip(),
            })
        return [x for x in out if x['guid']]

    def verify_project_membership(self, project_guid: str) -> dict[str, str]:
        guid = str(project_guid or '').strip()
        if not guid:
            raise ParatextAPIError('Paratext project GUID is required.')
        for project in self.list_projects():
            if project['guid'].casefold() == guid.casefold():
                return project
        raise ParatextAPIError('The configured Paratext GUID was not returned for this authenticated user. Check the project mapping and membership.')

    def post_notes(self, project_guid: str, notes_xml: str | Path) -> str:
        guid = str(project_guid or '').strip()
        if not guid:
            raise ParatextAPIError('Paratext project GUID is required.')
        payload = Path(notes_xml).read_bytes()
        token = self.acquire_token()
        url = f'{self.data_access_base}/api8/notes/{urllib.parse.quote(guid, safe="")}'
        req = urllib.request.Request(
            url,
            data=payload,
            method='POST',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/xml; charset=utf-8', 'Accept': 'text/plain'},
        )
        return self._request(req).decode('utf-8', 'replace').strip()
