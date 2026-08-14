from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Any


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ''
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


@dataclass
class JournalRecord:
    transaction_id: str
    label: str
    status: str
    journal_path: Path
    backup_root: Path
    paths: list[Path]
    existed: dict[str, bool]


class TransactionJournal:
    """Durable companion journal for project-mutating operations.

    A journal entry is persisted before project files are changed. A crash on the next
    launch can therefore be detected. Recovery is conservative: unfinished transactions
    are rolled back from the transaction backup rather than guessed/continued.
    """

    SCHEMA_VERSION = 1

    def __init__(self, project_root: Path, companion_root: Path):
        self.project_root = Path(project_root).resolve()
        self.root = Path(companion_root) / 'transactions'
        # Opening/scanning a project must be read-only. Create the journal directory lazily
        # only when a human-approved project mutation actually starts.

    def begin(self, label: str, paths: Iterable[Path]) -> JournalRecord:
        self.root.mkdir(parents=True, exist_ok=True)
        txid = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:8]
        journal_path = self.root / f'{txid}.json'
        backup_root = self.root / txid / 'backup'
        real_paths = [Path(p).resolve() for p in paths]
        existed: dict[str, bool] = {}
        files = []
        for p in real_paths:
            key = str(p)
            existed[key] = p.exists()
            rel = self._relative(p)
            if p.exists() and p.is_file():
                dst = backup_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
            files.append({'path': key, 'relativePath': str(rel), 'existed': p.exists(), 'sha256Before': _sha256(p)})
        payload = {
            'schemaVersion': self.SCHEMA_VERSION,
            'transactionId': txid,
            'label': label,
            'status': 'prepared',
            'createdTimestamp': _utc(),
            'projectRoot': str(self.project_root),
            'backupRoot': str(backup_root),
            'files': files,
        }
        _atomic_json(journal_path, payload)
        return JournalRecord(txid, label, 'prepared', journal_path, backup_root, real_paths, existed)

    def mark_writing(self, rec: JournalRecord) -> None:
        self._patch(rec.journal_path, status='writing', writingTimestamp=_utc())

    def commit(self, rec: JournalRecord, metadata: dict[str, Any] | None = None) -> None:
        files=[]
        for p in rec.paths:
            files.append({'path':str(p),'existsAfter':p.exists(),'sha256After':_sha256(p)})
        self._patch(rec.journal_path, status='committed', committedTimestamp=_utc(), filesAfter=files, metadata=metadata or {})

    def rollback(self, rec: JournalRecord, reason: str = '') -> None:
        errors=[]
        for p in rec.paths:
            try:
                rel=self._relative(p); src=rec.backup_root/rel
                if rec.existed.get(str(p),False):
                    if not src.exists(): raise RuntimeError(f'missing backup {src}')
                    p.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,p)
                elif p.exists():
                    if p.is_file(): p.unlink()
                    else: shutil.rmtree(p)
            except Exception as e:
                errors.append(f'{p}: {e}')
        status='rolled_back' if not errors else 'recovery_required'
        self._patch(rec.journal_path,status=status,rollbackTimestamp=_utc(),reason=reason,rollbackErrors=errors)
        if errors:
            raise RuntimeError('Transaction rollback incomplete: ' + '; '.join(errors))

    def pending(self) -> list[dict[str, Any]]:
        out=[]
        if not self.root.exists(): return out
        for p in sorted(self.root.glob('*.json')):
            try: d=json.loads(p.read_text('utf-8'))
            except Exception: continue
            if d.get('status') in ('prepared','writing','recovery_required'):
                d['_journalPath']=str(p); out.append(d)
        return out

    def recover_all(self) -> list[dict[str, Any]]:
        results=[]
        for d in self.pending():
            path=Path(d['_journalPath']); backup=Path(d.get('backupRoot',''))
            files=d.get('files',[]) if isinstance(d.get('files'),list) else []
            errors=[]
            for item in files:
                try:
                    target=Path(item['path']); rel=Path(item.get('relativePath') or target.name); src=backup/rel
                    if item.get('existed'):
                        if not src.exists(): raise RuntimeError(f'missing backup {src}')
                        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,target)
                    elif target.exists():
                        if target.is_file(): target.unlink()
                        else: shutil.rmtree(target)
                except Exception as e: errors.append(str(e))
            status='recovered_rollback' if not errors else 'recovery_required'
            self._patch(path,status=status,recoveredTimestamp=_utc(),recoveryErrors=errors)
            results.append({'transactionId':d.get('transactionId'),'status':status,'errors':errors})
        return results

    def _relative(self, path: Path) -> Path:
        try: return path.resolve().relative_to(self.project_root)
        except Exception: return Path('_external') / path.name

    @staticmethod
    def _patch(path: Path, **changes: Any) -> None:
        data=json.loads(path.read_text('utf-8')) if path.exists() else {}
        data.update(changes); _atomic_json(path,data)
