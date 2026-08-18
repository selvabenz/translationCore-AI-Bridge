from __future__ import annotations

import configparser
import re
from pathlib import Path
from typing import Any

_DOOR43_MAIL = re.compile(r'^(?:\d+\+)?([^@+]+)@noreply\.door43\.org$', re.I)
_REMOTE = re.compile(r'(?:https?://|ssh://|git@)(?:[^/@]+@)?(?:git\.door43\.org|door43\.org)[/:]([^/]+)/([^/]+?)(?:\.git)?$', re.I)


def detect_project_identity(project_path: str | Path) -> dict[str, Any]:
    """Read only non-secret Git identity/project-owner metadata from a tC project.

    This does not claim to be translationCore's live Electron login session. It intentionally
    labels the source so the UI never confuses project Git identity with an authenticated session.
    """
    path = Path(project_path)
    cfg_path = path / '.git' / 'config'
    result: dict[str, Any] = {
        'door43_username': '', 'git_name': '', 'git_email': '', 'repository_owner': '',
        'repository_name': '', 'source': 'not detected', 'confidence': 'none',
    }
    if not cfg_path.exists():
        return result
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(cfg_path, encoding='utf-8')
    except Exception:
        return result
    if parser.has_section('user'):
        result['git_name'] = parser.get('user', 'name', fallback='').strip()
        result['git_email'] = parser.get('user', 'email', fallback='').strip()
        m = _DOOR43_MAIL.match(result['git_email'])
        if m:
            result['door43_username'] = m.group(1)
            result['source'] = '.git/config user.email'
            result['confidence'] = 'high'
    for section in parser.sections():
        if not section.lower().startswith('remote '):
            continue
        url = parser.get(section, 'url', fallback='').strip()
        m = _REMOTE.search(url)
        if m:
            result['repository_owner'] = m.group(1)
            result['repository_name'] = m.group(2)
            if not result['source'] or result['source'] == 'not detected':
                result['source'] = '.git/config remote URL'
                result['confidence'] = 'medium'
            break
    return result
