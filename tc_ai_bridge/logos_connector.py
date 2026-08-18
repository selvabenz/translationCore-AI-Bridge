from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LogosConnectorError(RuntimeError):
    pass


# Standard USFM book identifiers -> Logos Bible data type parse names.
_USFM_TO_LOGOS = {
    'GEN':'Genesis','EXO':'Exodus','LEV':'Leviticus','NUM':'Numbers','DEU':'Deuteronomy',
    'JOS':'Joshua','JDG':'Judges','RUT':'Ruth','1SA':'1 Samuel','2SA':'2 Samuel','1KI':'1 Kings','2KI':'2 Kings',
    '1CH':'1 Chronicles','2CH':'2 Chronicles','EZR':'Ezra','NEH':'Nehemiah','EST':'Esther','JOB':'Job','PSA':'Psalms',
    'PRO':'Proverbs','ECC':'Ecclesiastes','SNG':'Song of Solomon','ISA':'Isaiah','JER':'Jeremiah','LAM':'Lamentations',
    'EZK':'Ezekiel','DAN':'Daniel','HOS':'Hosea','JOL':'Joel','AMO':'Amos','OBA':'Obadiah','JON':'Jonah','MIC':'Micah',
    'NAM':'Nahum','HAB':'Habakkuk','ZEP':'Zephaniah','HAG':'Haggai','ZEC':'Zechariah','MAL':'Malachi',
    'MAT':'Matthew','MRK':'Mark','LUK':'Luke','JHN':'John','ACT':'Acts','ROM':'Romans','1CO':'1 Corinthians',
    '2CO':'2 Corinthians','GAL':'Galatians','EPH':'Ephesians','PHP':'Philippians','COL':'Colossians',
    '1TH':'1 Thessalonians','2TH':'2 Thessalonians','1TI':'1 Timothy','2TI':'2 Timothy','TIT':'Titus','PHM':'Philemon',
    'HEB':'Hebrews','JAS':'James','1PE':'1 Peter','2PE':'2 Peter','1JN':'1 John','2JN':'2 John','3JN':'3 John',
    'JUD':'Jude','REV':'Revelation',
}

# COM BibleReferenceDetails.Book values documented by Logos.
_LOGOS_ABBR_TO_USFM = {
    'Ge':'GEN','Ex':'EXO','Le':'LEV','Nu':'NUM','Dt':'DEU','Jos':'JOS','Jdg':'JDG','Ru':'RUT','1Sa':'1SA','2Sa':'2SA',
    '1Ki':'1KI','2Ki':'2KI','1Ch':'1CH','2Ch':'2CH','Ezr':'EZR','Ne':'NEH','Es':'EST','Job':'JOB','Ps':'PSA','Pr':'PRO',
    'Ec':'ECC','So':'SNG','Is':'ISA','Je':'JER','La':'LAM','Eze':'EZK','Da':'DAN','Ho':'HOS','Joe':'JOL','Am':'AMO','Ob':'OBA',
    'Jon':'JON','Mic':'MIC','Na':'NAM','Hab':'HAB','Zep':'ZEP','Hag':'HAG','Zec':'ZEC','Mal':'MAL','Mt':'MAT','Mk':'MRK',
    'Lk':'LUK','Jn':'JHN','Ac':'ACT','Ro':'ROM','1Co':'1CO','2Co':'2CO','Ga':'GAL','Eph':'EPH','Php':'PHP','Col':'COL',
    '1Th':'1TH','2Th':'2TH','1Ti':'1TI','2Ti':'2TI','Tt':'TIT','Phm':'PHM','Heb':'HEB','Jas':'JAS','1Pe':'1PE','2Pe':'2PE',
    '1Jn':'1JN','2Jn':'2JN','3Jn':'3JN','Jud':'JUD','Re':'REV',
}
_LOGOS_ABBR_TO_USFM_CI = {k.lower(): v for k, v in _LOGOS_ABBR_TO_USFM.items()}
_REF_RE = re.compile(r'^([1-4]?[A-Z]{2,4})\s+(\d+):([0-9]+[A-Za-z]?)$', re.I)


def bridge_to_logos_reference(reference: str) -> str:
    m = _REF_RE.match(' '.join(str(reference or '').strip().upper().split()))
    if not m:
        raise LogosConnectorError(f'Unsupported Bridge Scripture reference: {reference!r}')
    book, chapter, verse = m.groups()
    name = _USFM_TO_LOGOS.get(book.upper())
    if not name:
        raise LogosConnectorError(f'Logos navigation does not have a standard mapping for USFM book {book.upper()}.')
    return f'{name} {int(chapter)}:{verse}'


def logos_state_to_bridge_reference(book_abbrev: str, chapter: str, verse: str) -> str:
    book = _LOGOS_ABBR_TO_USFM_CI.get(str(book_abbrev or '').strip().lower())
    if not book:
        return ''
    ch = str(chapter or '').strip()
    vs = str(verse or '').strip()
    if not ch.isdigit() or not re.fullmatch(r'[0-9]+[A-Za-z]?', vs):
        return ''
    return f'{book} {int(ch)}:{vs.lower() if vs[-1:].isalpha() else int(vs)}'


@dataclass
class LogosState:
    detected: bool = False
    connected: bool = False
    navigation_ready: bool = False
    api_version: int = 0
    reference: str = ''
    rendered_reference: str = ''
    panel_title: str = ''
    panel_kind: str = ''
    message: str = ''


class LogosConnectorClient:
    """Local Windows Logos COM connector using one hidden persistent PowerShell STA helper."""

    def __init__(self, script_path: Path | None = None, *, timeout: float = 3.5, startup_timeout: float = 10.0, navigation_timeout: float = 5.0, popen_factory=subprocess.Popen):
        self.script_path = Path(script_path) if script_path else self._default_script_path()
        self.timeout = float(timeout)
        self.startup_timeout = max(float(startup_timeout), self.timeout)
        self.navigation_timeout = max(float(navigation_timeout), self.timeout)
        self._popen_factory = popen_factory
        self._process = None
        self._responses: queue.Queue = queue.Queue()
        self._reader = None
        self._stderr_reader = None
        self._stderr_lines = deque(maxlen=16)
        self._lock = threading.Lock()
        self._generation = 0

    @staticmethod
    def _default_script_path() -> Path:
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
        return base / 'logos_connector' / 'logos_bridge.ps1'

    @property
    def running(self) -> bool:
        return bool(self._process is not None and self._process.poll() is None)

    def _powershell(self) -> str:
        system_root = os.environ.get('SystemRoot', r'C:\Windows')
        candidate = Path(system_root) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
        if candidate.exists():
            return str(candidate)
        return shutil.which('powershell.exe') or shutil.which('powershell') or ''

    def _start(self) -> bool:
        if self.running:
            return False
        if os.name != 'nt':
            raise LogosConnectorError('Logos live navigation is available only on Windows desktop.')
        if not self.script_path.exists():
            raise LogosConnectorError(f'Logos bridge helper is missing: {self.script_path}')
        powershell = self._powershell()
        if not powershell:
            raise LogosConnectorError('Windows PowerShell could not be found.')
        creationflags = int(getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        startupinfo = None
        if hasattr(subprocess, 'STARTUPINFO'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= int(getattr(subprocess, 'STARTF_USESHOWWINDOW', 0))
            startupinfo.wShowWindow = int(getattr(subprocess, 'SW_HIDE', 0))
        response_queue: queue.Queue = queue.Queue()
        stderr_lines = deque(maxlen=16)
        self._responses = response_queue
        self._stderr_lines = stderr_lines
        self._generation += 1
        generation = self._generation
        self._process = self._popen_factory(
            [powershell, '-NoLogo', '-NoProfile', '-NonInteractive', '-STA', '-ExecutionPolicy', 'Bypass', '-File', str(self.script_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
            creationflags=creationflags, startupinfo=startupinfo,
        )
        proc = self._process

        def stderr_reader():
            stream = getattr(proc, 'stderr', None)
            if stream is None:
                return
            try:
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    line = line.strip()
                    if line:
                        stderr_lines.append(line)
            except Exception:
                pass

        def reader():
            try:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    try:
                        response_queue.put(json.loads(line))
                    except Exception:
                        response_queue.put({'ok': False, 'error': 'Invalid response from Logos helper.'})
            finally:
                # The helper can fail before producing JSON (for example a PowerShell parser
                # or Add-Type error). Drain stderr briefly so the UI reports the real cause.
                # Every helper generation owns its queue/buffer. A dead reader from generation N
                # must never inject a synthetic 'stopped' response into generation N+1.
                try:
                    local_stderr_thread.join(timeout=0.20)
                except Exception:
                    pass
                detail = ' | '.join(list(stderr_lines)).strip()
                if len(detail) > 1600:
                    detail = detail[-1600:]
                message = f'Logos helper stopped (generation {generation}).'
                if detail:
                    message += ' PowerShell: ' + detail
                response_queue.put({'ok': False, 'error': message, 'generation': generation})

        local_stderr_thread = threading.Thread(target=stderr_reader, name=f'LogosBridgeStderr-{generation}', daemon=True)
        local_reader_thread = threading.Thread(target=reader, name=f'LogosBridgeReader-{generation}', daemon=True)
        self._stderr_reader = local_stderr_thread
        self._reader = local_reader_thread
        local_stderr_thread.start()
        local_reader_thread.start()
        return True

    def _stop_process(self) -> None:
        proc, self._process = self._process, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=0.8)
        except Exception:
            try: proc.kill()
            except Exception: pass

    def _request(self, action: str, **payload: Any) -> dict[str, Any]:
        with self._lock:
            started_new = self._start()
            proc = self._process
            response_queue = self._responses
            generation = self._generation
            if proc is None or proc.stdin is None:
                raise LogosConnectorError('Logos helper did not start.')
            request_timeout = self.startup_timeout if started_new else (self.navigation_timeout if action == 'navigate' else self.timeout)
            try:
                proc.stdin.write(json.dumps({'action': action, **payload}, ensure_ascii=False, separators=(',', ':')) + '\n')
                proc.stdin.flush()
                response = response_queue.get(timeout=request_timeout)
            except queue.Empty:
                self._stop_process()
                raise LogosConnectorError(f'Logos did not respond within the connector timeout ({request_timeout:.1f}s; helper generation {generation}).')
            except Exception as e:
                self._stop_process()
                raise LogosConnectorError(f'Could not communicate with Logos: {e}') from e
            if not isinstance(response, dict):
                raise LogosConnectorError('Logos returned an invalid connector response.')
            if not response.get('ok', False):
                raise LogosConnectorError(str(response.get('error') or 'Logos connector operation failed.'))
            return response

    @staticmethod
    def _state(response: dict[str, Any]) -> LogosState:
        reference = logos_state_to_bridge_reference(response.get('book_abbrev',''), response.get('chapter',''), response.get('verse',''))
        return LogosState(
            detected=bool(response.get('detected', response.get('connected', False))),
            connected=bool(response.get('connected', False)),
            navigation_ready=bool(response.get('navigation_ready', response.get('connected', False))),
            api_version=int(response.get('api_version', 0) or 0),
            reference=reference,
            rendered_reference=str(response.get('reference_rendered') or ''),
            panel_title=str(response.get('panel_title') or ''),
            panel_kind=str(response.get('panel_kind') or ''),
            message=str(response.get('message') or ''),
        )

    def get_state(self) -> LogosState:
        return self._state(self._request('state'))

    def set_reference(self, reference: str, *, origin_id: str = '') -> LogosState:
        logos_ref = bridge_to_logos_reference(reference)
        return self._state(self._request('navigate', reference=logos_ref, origin_id=str(origin_id or '')))

    def close(self) -> None:
        if not self.running:
            self._stop_process()
            return
        try:
            self._request('close')
        except Exception:
            pass
        finally:
            self._stop_process()
