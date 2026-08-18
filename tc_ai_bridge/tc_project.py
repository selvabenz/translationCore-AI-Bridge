from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from collections import Counter

from .usfm import whitespace_tokens

from .models import VerseAlignment
from .transaction_journal import TransactionJournal
from .paratext_notes import append_paratext_note, validate_notes_11, convert_comment_list_to_notes_11, convert_legacy_notes_11, EXTERNAL_NOTE_SOURCE
from .alignment_reliability import structural_issues, alignment_fingerprint


class ProjectError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    with path.open('r', encoding='utf-8-sig') as f:
        return json.load(f)


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        # Validate the exact bytes before replacement.
        _read_json(Path(temp_name))
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


@dataclass
class ProjectSummary:
    path: Path
    book_id: str
    book_name: str
    target_language: str
    tc_version: str
    edit_version: str

    @property
    def display_name(self) -> str:
        return f'{self.book_name} ({self.book_id}) — {self.target_language}'


class TranslationCoreProject:
    def __init__(self, project_path: str | Path):
        self.path = Path(project_path).resolve()
        manifest_path = self.path / 'manifest.json'
        if not manifest_path.exists():
            raise ProjectError(f'Not a translationCore project: {self.path}')
        self.manifest = _read_json(manifest_path)
        self.book_id = str(self.manifest.get('project', {}).get('id', '')).lower()
        if not self.book_id:
            raise ProjectError('manifest.json has no project.id')
        self.tc_dir = self.path / '.apps' / 'translationCore'
        self.alignment_dir = self.tc_dir / 'alignmentData' / self.book_id
        self.index_dir = self.tc_dir / 'index'
        self.check_dir = self.tc_dir / 'checkData'
        self.book_dir = self.path / self.book_id
        if not self.alignment_dir.exists():
            raise ProjectError(f'Missing alignmentData for {self.book_id}')
        self._index_cache: dict[str, list[dict[str, Any]]] = {}
        self._checks_by_verse_cache: dict[tuple[str, str], list[dict[str, Any]]] | None = None
        self.journal = TransactionJournal(self.path, self.companion_dir())

    @property
    def summary(self) -> ProjectSummary:
        target = self.manifest.get('target_language', {})
        return ProjectSummary(
            self.path,
            self.book_id,
            str(self.manifest.get('project', {}).get('name', self.book_id)),
            str(target.get('name') or target.get('id') or ''),
            str(self.manifest.get('tc_version', '')),
            str(self.manifest.get('tc_edit_version', '')),
        )

    def chapters(self) -> list[str]:
        chapters = [x.stem for x in self.alignment_dir.glob('*.json') if x.stem.isdigit()]
        return sorted(chapters, key=int)

    def chapter_path(self, chapter: str | int) -> Path:
        return self.alignment_dir / f'{chapter}.json'

    def load_alignment_chapter(self, chapter: str | int) -> dict[str, Any]:
        p = self.chapter_path(chapter)
        if not p.exists():
            raise ProjectError(f'Missing alignment chapter: {p}')
        data = _read_json(p)
        if not isinstance(data, dict):
            raise ProjectError(f'Invalid alignment chapter JSON: {p}')
        return data

    def verses(self, chapter: str | int) -> list[str]:
        data = self.load_alignment_chapter(chapter)
        def key(v: str):
            if str(v).isdigit(): return (0, int(v))
            if str(v) == 'front': return (-1, 0)
            return (1, str(v))
        return sorted((str(x) for x in data.keys()), key=key)

    def load_verse_alignment(self, chapter: str | int, verse: str | int) -> VerseAlignment:
        chapter_data = self.load_alignment_chapter(chapter)
        raw = chapter_data.get(str(verse))
        if raw is None:
            raise ProjectError(f'No alignment data for {self.book_id} {chapter}:{verse}')
        return VerseAlignment.from_dict(raw)

    def target_chapter(self, chapter: str | int) -> dict[str, Any]:
        p = self.book_dir / f'{chapter}.json'
        if not p.exists():
            return {}
        data = _read_json(p)
        return data if isinstance(data, dict) else {}

    def target_verse_text(self, chapter: str | int, verse: str | int) -> str:
        return str(self.target_chapter(chapter).get(str(verse), ''))

    def usfm_path(self) -> Path | None:
        candidates = list(self.path.glob('*.usfm')) + list(self.path.glob('*.USFM')) + list(self.path.glob('*.sfm')) + list(self.path.glob('*.SFM'))
        return candidates[0] if candidates else None

    def check_types(self) -> dict[str, int]:
        out: dict[str, int] = {}
        if self.check_dir.exists():
            for p in sorted(self.check_dir.iterdir()):
                if p.is_dir():
                    out[p.name] = sum(1 for _ in p.rglob('*.json'))
        return out

    def index_tools(self) -> dict[str, int]:
        out: dict[str, int] = {}
        if self.index_dir.exists():
            for p in sorted(self.index_dir.iterdir()):
                if p.is_dir():
                    out[p.name] = sum(1 for _ in p.rglob('*.json'))
        return out

    def _load_index_tool(self, tool: str) -> list[dict[str, Any]]:
        if tool in self._index_cache:
            return self._index_cache[tool]
        book_dir = self.index_dir / tool / self.book_id
        entries: list[dict[str, Any]] = []
        if book_dir.exists():
            for p in book_dir.glob('*.json'):
                if p.name == 'contextId.json':
                    continue
                try:
                    data = _read_json(p)
                except Exception:
                    continue
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'contextId' in item:
                            item = copy.deepcopy(item)
                            item['_index_file'] = p.name
                            entries.append(item)
        self._index_cache[tool] = entries
        return entries

    def _checks_by_verse(self) -> dict[tuple[str, str], list[dict[str, Any]]]:
        """Build a persistent in-memory verse index once per project session.

        The original translationCore indexes are grouped by check category rather than verse.
        Re-scanning thousands of entries for every verse is acceptable for one book but scales
        poorly to Bible-size projects, so production mode materializes this read-only lookup.
        """
        if self._checks_by_verse_cache is not None:
            return self._checks_by_verse_cache
        by: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for tool in ('translationNotes', 'translationWords'):
            for entry in self._load_index_tool(tool):
                ref = entry.get('contextId', {}).get('reference', {}) if isinstance(entry, dict) else {}
                key = (str(ref.get('chapter')), str(ref.get('verse')))
                by.setdefault(key, []).append(entry)
        self._checks_by_verse_cache = by
        return by

    def checks_for_verse(self, chapter: str | int, verse: str | int) -> list[dict[str, Any]]:
        return list(self._checks_by_verse().get((str(chapter), str(verse)), ()))

    def invalidate_index_cache(self) -> None:
        """Invalidate materialized check indexes after a translationCore index write."""
        self._index_cache.clear()
        self._checks_by_verse_cache = None

    def _state_files_for_verse(self, state_type: str, chapter: str | int, verse: str | int) -> list[Path]:
        p = self.check_dir / state_type / self.book_id / str(chapter) / str(verse)
        return sorted(p.glob('*.json')) if p.exists() else []

    def check_state_for_verse(self, chapter: str | int, verse: str | int) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for typ in ('selections', 'invalidated', 'comments', 'verseEdits'):
            vals = []
            for p in self._state_files_for_verse(typ, chapter, verse):
                try:
                    d = _read_json(p)
                    if isinstance(d, dict):
                        d['_file'] = str(p)
                        vals.append(d)
                except Exception:
                    pass
            out[typ] = vals
        return out

    def _serializable_check_state(self, chapter: str | int, verse: str | int) -> dict[str, list[dict[str, Any]]]:
        """Return tC check-state content without local filesystem paths, for deterministic fingerprints."""
        raw = self.check_state_for_verse(chapter, verse)
        out: dict[str, list[dict[str, Any]]] = {}
        for key, values in raw.items():
            clean = []
            for item in values:
                if not isinstance(item, dict):
                    continue
                d = copy.deepcopy(item)
                d.pop('_file', None)
                clean.append(d)
            out[key] = clean
        return out

    def decisions_for_verse(self, chapter: str | int, verse: str | int) -> list[dict[str, Any]]:
        root = self.companion_dir() / 'decisions' / self.book_id / str(chapter) / str(verse)
        out: list[dict[str, Any]] = []
        if not root.exists():
            return out
        for path in sorted(root.glob('*.json')):
            try:
                d = _read_json(path)
                if isinstance(d, dict):
                    out.append(d)
            except Exception:
                pass
        return out

    def review_input_fingerprint(self, chapter: str | int, verse: str | int) -> str:
        """Fingerprint all project inputs that can materially change an AI verse review.

        It intentionally excludes model output and timestamps. A Scripture/alignment/check-state/
        project-version/human-decision change makes a cached review stale.
        """
        alignment_raw = self.load_alignment_chapter(chapter).get(str(verse), {})
        checks = []
        for entry in self.checks_for_verse(chapter, verse):
            if not isinstance(entry, dict):
                continue
            checks.append({
                'contextId': copy.deepcopy(entry.get('contextId', {})),
                'selections': copy.deepcopy(entry.get('selections', False)),
                'nothingToSelect': bool(entry.get('nothingToSelect', False)),
                'invalidated': copy.deepcopy(entry.get('invalidated', False)),
                'verseEdits': copy.deepcopy(entry.get('verseEdits', False)),
                'comments': copy.deepcopy(entry.get('comments', False)),
            })
        version_manifest = {
            k: copy.deepcopy(v) for k, v in self.manifest.items()
            if k.startswith('tc_') or k in ('source_translations', 'target_language', 'resource', 'project')
        }
        resource_dirs = {}
        helps = self.path.parent.parent / 'resources' / 'en' / 'translationHelps'
        if helps.exists():
            for name in ('translationAcademy','translationNotes','translationWords','translationWordsLinks'):
                rd=helps/name
                if rd.exists():
                    vals=[]
                    for q in sorted((x for x in rd.iterdir() if x.is_dir()), key=lambda x:x.name):
                        try: vals.append((q.name,q.stat().st_mtime_ns))
                        except Exception: vals.append((q.name,0))
                    resource_dirs[name]=vals
        payload = {
            'bookId': self.book_id,
            'chapter': str(chapter),
            'verse': str(verse),
            'targetText': self.target_verse_text(chapter, verse),
            'alignment': alignment_raw,
            'checks': checks,
            'checkState': self._serializable_check_state(chapter, verse),
            'manifestVersions': version_manifest,
            'installedTranslationHelps': resource_dirs,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    def ai_review_cache_status(self, chapter: str | int, verse: str | int) -> str:
        """Return missing | current | stale for the locally cached AI review."""
        saved = self.load_ai_review_result(chapter, verse)
        if not saved:
            return 'missing'
        saved_fp = str(saved.get('inputFingerprint') or '')
        if not saved_fp:
            return 'stale'
        try:
            return 'current' if saved_fp == self.review_input_fingerprint(chapter, verse) else 'stale'
        except Exception:
            return 'stale'

    @staticmethod
    def _alignment_work_state(alignment: VerseAlignment) -> str:
        aligned_bottom = alignment.aligned_bottom()
        if not aligned_bottom:
            return 'untouched'
        incomplete_top = any(g.top_words and not g.bottom_words for g in alignment.alignments)
        if alignment.word_bank or incomplete_top:
            return 'partial'
        return 'complete'

    def verse_work_state(self, chapter: str | int, verse: str | int) -> str:
        states = self.check_state_for_verse(chapter, verse)
        indexed = self.checks_for_verse(chapter, verse)
        if self.word_alignment_state(chapter, verse) == 'invalid':
            return 'STALE_AFTER_VERSE_EDIT'
        if any(self.check_staleness(chapter, verse, str(e.get('contextId',{}).get('checkId',''))) == 'stale' for e in indexed):
            return 'STALE_AFTER_VERSE_EDIT'
        if states.get('invalidated') or any(bool(e.get('invalidated')) for e in indexed):
            return 'STALE_RECHECK_REQUIRED'
        review_state = self.load_review_state(chapter, verse)
        if review_state and str(review_state.get('status', '')).lower() in ('approved', 'human_approved'):
            return 'HUMAN_APPROVED'
        cache = self.ai_review_cache_status(chapter, verse)
        if cache == 'current':
            return 'AI_PREPARED'
        alignment_state = self._alignment_work_state(self.load_verse_alignment(chapter, verse))
        checked = any(isinstance(e.get('selections'), list) or bool(e.get('nothingToSelect')) for e in indexed)
        if alignment_state == 'untouched' and not checked:
            return 'UNTOUCHED'
        return 'PARTIALLY_WORKED'

    def project_scan(self) -> dict[str, Any]:
        """Scan existing translationCore + companion state for reviewer planning.

        This is intentionally deterministic and makes no API calls.
        """
        result: dict[str, Any] = {
            'bookId': self.book_id,
            'verses': 0,
            'alignment': {'complete': 0, 'partial': 0, 'untouched': 0},
            'translationNotes': {'total': 0, 'checked': 0, 'pending': 0, 'invalidated': 0},
            'translationWords': {'total': 0, 'checked': 0, 'pending': 0, 'invalidated': 0},
            'aiReview': {'current': 0, 'stale': 0, 'missing': 0},
            'workState': {},
            'humanDecisions': {'accepted': 0, 'needs_discussion': 0, 'rejected': 0, 'other': 0},
            'verseEdits': 0,
            'comments': 0,
            'pendingTransactions': len(self.pending_transactions()),
        }
        for ch in self.chapters():
            for vs in self.verses(ch):
                if str(vs) == 'front':
                    continue
                result['verses'] += 1
                alignment_state = self._alignment_work_state(self.load_verse_alignment(ch, vs))
                result['alignment'][alignment_state] += 1
                for entry in self.checks_for_verse(ch, vs):
                    tool = str(entry.get('contextId', {}).get('tool') or '')
                    bucket = result.get(tool)
                    if not isinstance(bucket, dict):
                        continue
                    bucket['total'] += 1
                    invalid = bool(entry.get('invalidated', False))
                    cid = str(entry.get('contextId',{}).get('checkId',''))
                    stale = self.check_staleness(ch, vs, cid) == 'stale'
                    checked = isinstance(entry.get('selections'), list) or bool(entry.get('nothingToSelect', False))
                    if invalid or stale:
                        bucket['invalidated'] += 1
                    if checked and not invalid and not stale:
                        bucket['checked'] += 1
                    else:
                        bucket['pending'] += 1
                cache = self.ai_review_cache_status(ch, vs)
                result['aiReview'][cache] += 1
                work = self.verse_work_state(ch, vs)
                result['workState'][work] = int(result['workState'].get(work, 0)) + 1
                states = self.check_state_for_verse(ch, vs)
                result['verseEdits'] += len(states.get('verseEdits', []))
                result['comments'] += len(states.get('comments', []))
        for d in self.project_decisions():
            decision = str(d.get('decision') or '').lower()
            key = decision if decision in ('accepted', 'needs_discussion', 'rejected') else 'other'
            result['humanDecisions'][key] += 1
        return result

    def alignment_lock_state(self, chapter: str | int, verse: str | int) -> str:
        """Classify existing work for v0.7.4 without rewriting it."""
        alignment = self.load_verse_alignment(chapter, verse)
        review = self.load_review_state(chapter, verse) or {}
        if str(review.get('status', '')).lower() in ('approved', 'human_approved'):
            return 'HARD_LOCK'
        state = self._alignment_work_state(alignment)
        if state == 'complete' or self.word_alignment_state(chapter, verse) == 'completed':
            return 'PROTECTED_LEGACY'
        if state == 'partial':
            return 'PARTIAL_PROTECTED'
        return 'OPEN'

    def alignment_compatibility_scan(self) -> dict[str, Any]:
        """Read-only v0.7.4 compatibility scan for existing alignment work."""
        result: dict[str, Any] = {
            'bookId': self.book_id,
            'verses': 0,
            'hardLocked': 0,
            'protectedLegacy': 0,
            'partialProtected': 0,
            'open': 0,
            'stale': 0,
            'structuralReview': 0,
            'malformed': 0,
            'exceptions': [],
            'filesModified': 0,
        }
        for ch in self.chapters():
            for vs in self.verses(ch):
                if str(vs) == 'front':
                    continue
                result['verses'] += 1
                try:
                    alignment = self.load_verse_alignment(ch, vs)
                    issues = structural_issues(alignment)
                    lock = self.alignment_lock_state(ch, vs)
                    if lock == 'HARD_LOCK': result['hardLocked'] += 1
                    elif lock == 'PROTECTED_LEGACY': result['protectedLegacy'] += 1
                    elif lock == 'PARTIAL_PROTECTED': result['partialProtected'] += 1
                    else: result['open'] += 1
                    stale = self.word_alignment_state(ch, vs) == 'invalid'
                    if stale:
                        result['stale'] += 1
                    if issues:
                        result['structuralReview'] += 1
                    if stale or issues:
                        result['exceptions'].append({
                            'chapter': str(ch), 'verse': str(vs), 'lock': lock,
                            'stale': stale, 'issues': issues,
                        })
                except Exception as exc:
                    result['malformed'] += 1
                    result['exceptions'].append({
                        'chapter': str(ch), 'verse': str(vs), 'lock': 'UNKNOWN',
                        'stale': False, 'issues': [str(exc)],
                    })
        return result

    def ensure_v073_migration_snapshot(self) -> Path:
        """Create a hash-only compatibility snapshot; never rewrites alignment/project data."""
        root = self.companion_dir() / 'migration' / 'pre-v073'
        path = root / f'{self.book_id}.json'
        if path.exists():
            return path
        chapters: dict[str, Any] = {}
        for ch in self.chapters():
            cp = self.chapter_path(ch)
            try:
                raw = cp.read_bytes()
                chapters[str(ch)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            except Exception as exc:
                chapters[str(ch)] = {'error': str(exc)}
        data = {
            'bookId': self.book_id,
            'projectPath': str(self.path),
            'createdTimestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'purpose': 'v0.7.4 existing-work protection snapshot; hashes only; no project data rewritten',
            'chapters': chapters,
        }
        _write_json_atomic(path, data)
        return path

    def record_alignment_diagnostic(self, chapter: str | int, verse: str | int, payload: dict[str, Any]) -> Path:
        """Persist non-secret compiler diagnostics for field reliability analysis."""
        iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        safe = iso.replace(':', '_').replace('.', '_')
        data = {
            'bookId': self.book_id, 'chapter': str(chapter), 'verse': str(verse),
            'timestamp': iso, 'app': 'translationCore AI Bridge', 'schemaVersion': 1,
            **copy.deepcopy(payload),
        }
        path = self.companion_dir() / 'alignmentDiagnostics' / self.book_id / str(chapter) / str(verse) / f'{safe}.json'
        _write_json_atomic(path, data)
        return path

    def recover_incomplete_transactions(self) -> list[dict[str, Any]]:
        """Roll back any transaction left unfinished by a prior crash/power loss."""
        out = self.journal.recover_all()
        if out:
            self._index_cache.clear(); self._checks_by_verse_cache = None
        return out

    def pending_transactions(self) -> list[dict[str, Any]]:
        return self.journal.pending()

    def sync_comment(self, chapter: str | int, verse: str | int, context_id: dict[str, Any], text: str, username: str = 'AI Bridge Reviewer', gateway_language_code: str = 'en', gateway_language_quote: str = '') -> Path:
        """Append a native translationCore comment using the observed checkData/comments shape.

        This never completes a check. It is appropriate for reviewer discussion notes and
        rejection rationale attached to a concrete TN/TW contextId.
        """
        text=str(text).strip()
        if not text:
            raise ProjectError('Comment text may not be empty.')
        ctx=copy.deepcopy(context_id or {})
        ref=ctx.get('reference',{}) if isinstance(ctx,dict) else {}
        if str(ref.get('bookId',self.book_id)).lower()!=self.book_id or str(ref.get('chapter'))!=str(chapter) or str(ref.get('verse'))!=str(verse):
            raise ProjectError('Comment contextId does not match the current verse.')
        if str(ctx.get('tool','')) not in ('translationNotes','translationWords'):
            raise ProjectError('Native translationCore comments require a Translation Notes/Words contextId.')
        iso,safe=self._timestamp()
        path=self.check_dir/'comments'/self.book_id/str(chapter)/str(verse)/f'{safe}.json'
        rec={
            'text':text,'username':username,'activeBook':self.book_id,
            'activeChapter':int(chapter) if str(chapter).isdigit() else str(chapter),
            'activeVerse':int(verse) if str(verse).isdigit() else str(verse),
            'modifiedTimestamp':iso,'gatewayLanguageCode':gateway_language_code,
            'gatewayLanguageQuote':gateway_language_quote,'contextId':ctx,
        }
        tx=self.journal.begin('tcCommentSync',[path]); self.journal.mark_writing(tx)
        try:
            _write_json_atomic(path,rec)
            reread=_read_json(path)
            if reread.get('contextId',{}).get('checkId')!=ctx.get('checkId'):
                raise ProjectError('Post-write translationCore comment verification failed.')
            self.journal.commit(tx,{'operation':'tcCommentSync','checkId':ctx.get('checkId','')})
        except Exception as e:
            self.journal.rollback(tx,str(e)); raise
        audit=self.companion_dir()/'audit'/self.book_id/str(chapter)/str(verse)/f'{safe}_tc-comment.json'
        _write_json_atomic(audit,{'operation':'tcCommentSync','path':str(path),'text':text,'username':username,'modifiedTimestamp':iso,'contextId':ctx})
        return path


    def _target_language_code(self) -> str:
        target = self.manifest.get('target_language') if isinstance(self.manifest, dict) else None
        if isinstance(target, dict):
            value = target.get('id') or target.get('language_id') or target.get('identifier')
            if value:
                return str(value).strip()
        for key in ('target_language_id', 'language_id', 'languageId'):
            value = self.manifest.get(key) if isinstance(self.manifest, dict) else None
            if value:
                return str(value).strip()
        return 'und'

    def _legacy_paratext_notes_path(self) -> Path:
        return self.companion_dir() / 'paratextNotes' / f'{self.book_id}.notes.xml'

    def _legacy_paratext_commentlist_path(self) -> Path:
        return self.companion_dir() / 'paratextNotes' / f'{self.book_id}.comments.xml'

    def record_paratext_note(self, chapter: str | int, verse: str | int, text: str, username: str = 'AI Bridge Reviewer', selected_text: str = '', note_type: str = '', metadata: dict[str, Any] | None = None, assigned_user: str = '', reply_to_user: str = '', ext_user: str = EXTERNAL_NOTE_SOURCE) -> Path:
        """Record an API-ready Paratext Notes 1.1 project note.

        ``username`` is stored as the best-known Paratext author hint in the companion XML. Live
        Plugin API synchronization does not impersonate that value: Paratext itself records the
        current logged-in Paratext user as the real Project Note author. API-ready XML export also
        normalizes ``comment@user`` to a real detected/configured Paratext member. ``ext_user``
        identifies the external AI origin. The target Scripture text is never modified by note
        creation.
        """
        path = self.paratext_notes_path()
        old_commentlist = self._legacy_paratext_commentlist_path()
        old_notes = self._legacy_paratext_notes_path()

        # Upgrade existing companion data once. v0.7.1 wrote CommentList exports; v0.7.0 wrote
        # Notes 1.1. Preserve the old files and create the corrected primary Notes file.
        if not path.exists():
            if old_commentlist.exists():
                convert_comment_list_to_notes_11(old_commentlist, path, ext_user=ext_user)
            elif old_notes.exists():
                convert_legacy_notes_11(old_notes, path, language=self._target_language_code())

        tx = self.journal.begin('paratextNote', [path]); self.journal.mark_writing(tx)
        try:
            out, thread_id = append_paratext_note(
                path, book_id=self.book_id, chapter=chapter, verse=verse,
                verse_text=self.target_verse_text(chapter, verse), comment_text=text, reviewer=username,
                selected_text=selected_text, language=self._target_language_code(), note_type=str((metadata or {}).get('paratextThreadType') or ''),
                assigned_user=assigned_user, reply_to_user=reply_to_user, metadata=metadata, ext_user=ext_user,
            )
            check = validate_notes_11(out)
            self.journal.commit(tx, {'operation': 'paratextNotes11', 'threadId': thread_id, 'threads': check['threads'], 'comments': check['comments']})
            return out
        except Exception as e:
            self.journal.rollback(tx, str(e)); raise

    def paratext_notes_path(self) -> Path:
        # This is a Bridge companion/export filename only. Direct Paratext synchronization uses
        # the project GUID + Notes 1.1 API and does not depend on a guessed Paratext project file.
        return self.companion_dir() / 'paratextNotes' / 'Notes_AI_Suggestion.xml'

    def paratext_note_sync_state_path(self) -> Path:
        return self.companion_dir() / 'paratextNotes' / 'live_sync_state.json'

    def load_paratext_note_sync_state(self) -> dict[str, Any]:
        path = self.paratext_note_sync_state_path()
        if not path.exists():
            return {'version': 1, 'items': {}}
        try:
            data = _read_json(path)
        except Exception:
            return {'version': 1, 'items': {}}
        if not isinstance(data, dict):
            return {'version': 1, 'items': {}}
        items = data.get('items')
        if not isinstance(items, dict):
            items = {}
        return {'version': 1, 'items': dict(items)}

    def save_paratext_note_sync_state(self, data: dict[str, Any]) -> Path:
        path = self.paratext_note_sync_state_path()
        payload = {'version': 1, 'items': dict((data or {}).get('items') or {})}
        _write_json_atomic(path, payload)
        return path

    def comments_for_check(self, chapter: str | int, verse: str | int, check_id: str) -> list[dict[str, Any]]:
        out=[]
        for item in self.check_state_for_verse(chapter,verse).get('comments',[]):
            if str(item.get('contextId',{}).get('checkId',''))==str(check_id): out.append(item)
        return out

    def companion_dir(self) -> Path:
        return self.path / '.apps' / 'translationCoreAI'

    def backup_chapter(self, chapter: str | int) -> Path:
        src = self.chapter_path(chapter)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        dst = self.companion_dir() / 'backups' / stamp / 'alignmentData' / self.book_id / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return dst

    def save_verse_alignment(self, chapter: str | int, verse: str | int, value: VerseAlignment, expected_original: dict[str, Any] | None = None) -> Path:
        chapter_path = self.chapter_path(chapter)
        chapter_data = self.load_alignment_chapter(chapter)
        if expected_original is not None:
            current = chapter_data.get(str(verse))
            if current != expected_original:
                raise ProjectError('The alignment file changed on disk after it was loaded. Reload before saving to avoid overwriting another edit.')
        # Validate model serialization before touching disk.
        raw = value.to_dict()
        self._validate_verse_raw(raw)
        backup = self.backup_chapter(chapter)
        tx = self.journal.begin('saveApprovedAlignment', [chapter_path])
        self.journal.mark_writing(tx)
        try:
            chapter_data[str(verse)] = raw
            _write_json_atomic(chapter_path, chapter_data)
            # Re-read and validate after write.
            written = self.load_alignment_chapter(chapter).get(str(verse))
            self._validate_verse_raw(written)
            self.journal.commit(tx, {'operation':'saveApprovedAlignment','chapter':str(chapter),'verse':str(verse)})
        except Exception as e:
            self.journal.rollback(tx, str(e)); raise
        return backup

    @staticmethod
    def _validate_verse_raw(raw: Any) -> None:
        if not isinstance(raw, dict):
            raise ProjectError('Verse alignment must be an object')
        if not isinstance(raw.get('alignments'), list) or not isinstance(raw.get('wordBank'), list):
            raise ProjectError('Verse alignment must contain alignments[] and wordBank[]')
        for i, group in enumerate(raw['alignments']):
            if not isinstance(group, dict) or not isinstance(group.get('topWords'), list) or not isinstance(group.get('bottomWords'), list):
                raise ProjectError(f'Invalid alignment group {i}')
            for side in ('topWords', 'bottomWords'):
                for token in group[side]:
                    if not isinstance(token, dict) or not token.get('word'):
                        raise ProjectError(f'Invalid token in group {i}/{side}')
                    if int(token.get('occurrence', 0)) < 1 or int(token.get('occurrences', 0)) < 1:
                        raise ProjectError(f'Invalid occurrence metadata in group {i}/{side}')
        for token in raw['wordBank']:
            if not isinstance(token, dict) or not token.get('word'):
                raise ProjectError('Invalid wordBank token')


    def list_alignment_backups(self, chapter: str | int) -> list[Path]:
        root = self.companion_dir() / 'backups'
        if not root.exists():
            return []
        found = list(root.glob(f'*/alignmentData/{self.book_id}/{chapter}.json'))
        return sorted(found, key=lambda x: x.parts[-4], reverse=True)

    def restore_alignment_backup(self, chapter: str | int, backup_path: str | Path) -> Path:
        backup = Path(backup_path).resolve()
        allowed_root = (self.companion_dir() / 'backups').resolve()
        try:
            backup.relative_to(allowed_root)
        except ValueError as e:
            raise ProjectError('Refusing to restore a file outside translationCoreAI/backups.') from e
        if not backup.exists() or backup.name != f'{chapter}.json':
            raise ProjectError('Selected backup does not match the current chapter.')
        data = _read_json(backup)
        if not isinstance(data, dict):
            raise ProjectError('Backup is not a valid alignment chapter object.')
        for raw in data.values():
            self._validate_verse_raw(raw)
        # Preserve the current chapter before rolling back so restore itself is reversible.
        safety_backup = self.backup_chapter(chapter)
        _write_json_atomic(self.chapter_path(chapter), data)
        reread = self.load_alignment_chapter(chapter)
        if reread != data:
            raise ProjectError('Post-restore verification failed.')
        return safety_backup

    def load_review_state(self, chapter: str | int, verse: str | int) -> dict[str, Any] | None:
        p = self.companion_dir() / 'review' / self.book_id / str(chapter) / f'{verse}.json'
        if not p.exists():
            return None
        try:
            d = _read_json(p)
            return d if isinstance(d, dict) else None
        except Exception:
            return None

    def record_review_state(self, chapter: str | int, verse: str | int, status: str, note: str = '') -> Path:
        data = {
            'bookId': self.book_id,
            'chapter': str(chapter),
            'verse': str(verse),
            'status': status,
            'note': note,
            'modifiedTimestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'app': 'translationCore AI Bridge',
            'schemaVersion': 1,
        }
        p = self.companion_dir() / 'review' / self.book_id / str(chapter) / f'{verse}.json'
        _write_json_atomic(p, data)
        stamp = str(data['modifiedTimestamp']).replace(':','_').replace('.','_')
        audit = self.companion_dir() / 'audit' / self.book_id / str(chapter) / str(verse) / f'{stamp}_verse-status.json'
        _write_json_atomic(audit, data)
        return p

    def record_ai_review_result(self, chapter: str | int, verse: str | int, payload: dict[str, Any]) -> Path:
        data = {
            'bookId': self.book_id,
            'chapter': str(chapter),
            'verse': str(verse),
            'generatedTimestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'inputFingerprint': self.review_input_fingerprint(chapter, verse),
            'app': 'translationCore AI Bridge',
            'schemaVersion': 3,
            **copy.deepcopy(payload),
        }
        p = self.companion_dir() / 'aiReview' / self.book_id / str(chapter) / f'{verse}.json'
        _write_json_atomic(p, data)
        return p

    def load_ai_review_result(self, chapter: str | int, verse: str | int) -> dict[str, Any] | None:
        p = self.companion_dir() / 'aiReview' / self.book_id / str(chapter) / f'{verse}.json'
        if not p.exists():
            return None
        try:
            d = _read_json(p)
            return d if isinstance(d, dict) else None
        except Exception:
            return None

    def record_human_decision(self, chapter: str | int, verse: str | int, check_id: str, decision: str, note: str = '', selection_text: list[str] | None = None, selection_ids: list[str] | None = None, tool: str = '', group_id: str = '', model: str = '', evidence: list[dict[str, Any]] | None = None) -> Path:
        stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        compact_evidence = []
        for ev in list(evidence or []):
            if not isinstance(ev, dict):
                continue
            compact_evidence.append({k: copy.deepcopy(ev.get(k)) for k in ('kind','title','path','version','provider','identifier','authoritative') if ev.get(k) not in (None,'')})
        data = {
            'bookId': self.book_id,
            'chapter': str(chapter),
            'verse': str(verse),
            'checkId': str(check_id),
            'tool': str(tool),
            'groupId': str(group_id),
            'decision': str(decision),
            'note': str(note),
            'selectionText': list(selection_text or []),
            'selectionIds': list(selection_ids or []),
            'model': str(model),
            'evidenceProvenance': compact_evidence,
            'modifiedTimestamp': stamp,
            'app': 'translationCore AI Bridge',
            'schemaVersion': 2,
        }
        safe_id = ''.join(ch if ch.isalnum() or ch in ('-','_') else '_' for ch in str(check_id)) or 'verse'
        p = self.companion_dir() / 'decisions' / self.book_id / str(chapter) / str(verse) / f'{safe_id}.json'
        _write_json_atomic(p, data)
        # Append-only audit history: the latest decision remains easy to read, while earlier
        # AI/human states are never lost when the reviewer changes a decision later.
        safe_stamp = stamp.replace(':','_').replace('.','_')
        audit = self.companion_dir() / 'audit' / self.book_id / str(chapter) / str(verse) / f'{safe_stamp}_{safe_id}.json'
        _write_json_atomic(audit, data)
        return p

    def rebase_ai_review_fingerprint(self, chapter: str | int, verse: str | int) -> None:
        """Keep an already-reviewed verse current after human-only TN/TW state synchronization."""
        p = self.companion_dir() / 'aiReview' / self.book_id / str(chapter) / f'{verse}.json'
        if not p.exists(): return
        d = _read_json(p)
        if isinstance(d, dict):
            d['inputFingerprint'] = self.review_input_fingerprint(chapter, verse)
            d['humanStateRebasedTimestamp'] = datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
            _write_json_atomic(p, d)

    def list_ai_review_results(self, chapter: str | int | None = None) -> list[dict[str, Any]]:
        root = self.companion_dir() / 'aiReview' / self.book_id
        if chapter is not None:
            root = root / str(chapter)
        out: list[dict[str, Any]] = []
        if not root.exists():
            return out
        for p in sorted(root.rglob('*.json')):
            try:
                d = _read_json(p)
                if isinstance(d, dict):
                    out.append(d)
            except Exception:
                pass
        return out

    def terminology_rules(self) -> list[dict[str, Any]]:
        root = self.companion_dir() / 'terminology' / self.book_id
        out: list[dict[str, Any]] = []
        if not root.exists(): return out
        for p in sorted(root.glob('*.json')):
            try:
                d=_read_json(p)
                if isinstance(d,dict): out.append(d)
            except Exception: pass
        return out

    def record_terminology_rule(self, concept_id: str, approved_renderings: list[str], allowed_alternatives: list[str] | None = None, rejected_renderings: list[str] | None = None, source_lemma: str = '', strong: str = '', note: str = '', username: str = 'AI Bridge Reviewer', scope: str = 'book') -> Path:
        concept_id=str(concept_id).strip()
        approved=[str(x).strip() for x in approved_renderings if str(x).strip()]
        if not concept_id: raise ProjectError('Terminology concept/key-term ID is required.')
        if not approved: raise ProjectError('At least one approved target-language rendering is required.')
        iso,_=self._timestamp(); safe=''.join(ch if ch.isalnum() or ch in ('-','_') else '_' for ch in concept_id)[:120]
        data={
            'bookId':self.book_id,'conceptId':concept_id,'sourceLemma':source_lemma,'strong':strong,
            'approvedRenderings':approved,'allowedAlternatives':[str(x).strip() for x in (allowed_alternatives or []) if str(x).strip()],
            'rejectedRenderings':[str(x).strip() for x in (rejected_renderings or []) if str(x).strip()],
            'note':note,'scope':scope,'username':username,'modifiedTimestamp':iso,'status':'human_approved',
            'app':'translationCore AI Bridge','schemaVersion':1,
        }
        p=self.companion_dir()/'terminology'/self.book_id/f'{safe}.json'; _write_json_atomic(p,data)
        audit=self.companion_dir()/'audit'/self.book_id/'terminology'/f"{iso.replace(':','_').replace('.','_')}_{safe}.json"; _write_json_atomic(audit,data)
        return p

    def project_decisions(self) -> list[dict[str, Any]]:
        root = self.companion_dir() / 'decisions' / self.book_id
        out: list[dict[str, Any]] = []
        if not root.exists():
            return out
        for p in root.rglob('*.json'):
            try:
                d = _read_json(p)
                if isinstance(d, dict):
                    out.append(d)
            except Exception:
                pass
        return out

    def _timestamp(self) -> tuple[str, str]:
        iso = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        return iso, iso.replace(':', '_')

    def _backup_paths(self, paths: list[Path], label: str) -> Path:
        """Back up existing project files before a multi-file tC-compatible transaction."""
        iso, safe = self._timestamp()
        root = self.companion_dir() / 'backups' / safe / label
        for path in paths:
            if not path.exists():
                continue
            try:
                rel = path.resolve().relative_to(self.path)
            except Exception:
                rel = Path(path.name)
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
        return root

    def _rollback_paths(self, backup_root: Path, paths: list[Path], existed: dict[str, bool]) -> None:
        errors=[]
        for path in paths:
            try:
                key=str(path.resolve())
                rel=path.resolve().relative_to(self.path)
                src=backup_root/rel
                if existed.get(key,False):
                    if not src.exists(): raise ProjectError(f'Missing rollback copy for {path}')
                    path.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,path)
                elif path.exists():
                    path.unlink()
            except Exception as e:
                errors.append(f'{path}: {e}')
        if errors:
            raise ProjectError('Rollback was incomplete; restore from backup '+str(backup_root)+'\n'+'\n'.join(errors))

    def _find_index_entry_path(self, tool: str, group_id: str, check_id: str) -> tuple[Path, list[dict[str, Any]], int]:
        path = self.index_dir / tool / self.book_id / f'{group_id}.json'
        if not path.exists():
            raise ProjectError(f'Missing translationCore index file for {tool}/{group_id}')
        data = _read_json(path)
        if not isinstance(data, list):
            raise ProjectError(f'Invalid translationCore index list: {path}')
        for i, entry in enumerate(data):
            if isinstance(entry, dict) and str(entry.get('contextId', {}).get('checkId', '')) == str(check_id):
                return path, data, i
        raise ProjectError(f'Could not find check {check_id} in {tool}/{group_id}')

    def _latest_state_for_check(self, state_type: str, chapter: str | int, verse: str | int, check_id: str) -> dict[str, Any] | None:
        latest = None
        latest_ts = ''
        for path in self._state_files_for_verse(state_type, chapter, verse):
            try:
                d = _read_json(path)
            except Exception:
                continue
            if str(d.get('contextId', {}).get('checkId', '')) != str(check_id):
                continue
            ts = str(d.get('modifiedTimestamp') or d.get('timestamp') or path.name)
            if ts >= latest_ts:
                latest, latest_ts = d, ts
        return latest

    def check_staleness(self, chapter: str | int, verse: str | int, check_id: str) -> str:
        """current | stale | pending using actual tC selection vs verse-edit timestamps."""
        sel = self._latest_state_for_check('selections', chapter, verse, check_id)
        if not sel:
            return 'pending'
        sel_ts = str(sel.get('modifiedTimestamp', ''))
        edit_ts = ''
        for path in self._state_files_for_verse('verseEdits', chapter, verse):
            try:
                d = _read_json(path)
            except Exception:
                continue
            edit_ts = max(edit_ts, str(d.get('modifiedTimestamp', '')))
        return 'stale' if edit_ts and sel_ts <= edit_ts else 'current'

    def sync_check_approval(self, chapter: str | int, verse: str | int, tool: str, group_id: str, check_id: str, selections: list[dict[str, Any]], nothing_to_select: bool, username: str = 'AI Bridge Reviewer', gateway_language_code: str = 'en', gateway_language_quote: str = '') -> dict[str, str]:
        """Write a human-approved TN/TW result using the observed translationCore v8 lifecycle.

        Appends matching selections + invalidated(false) state records and updates the persisted
        tool index entry. Existing history is never deleted.
        """
        if tool not in ('translationNotes', 'translationWords'):
            raise ProjectError('Only Translation Notes/Words checks can be synchronized here.')
        path, data, idx = self._find_index_entry_path(tool, group_id, check_id)
        entry = data[idx]
        ctx = copy.deepcopy(entry.get('contextId', {}))
        ref = ctx.get('reference', {})
        if str(ref.get('chapter')) != str(chapter) or str(ref.get('verse')) != str(verse):
            raise ProjectError('Check reference does not match the current verse.')
        if nothing_to_select and selections:
            raise ProjectError('nothingToSelect cannot be true when selections are present.')
        for item in selections:
            if not isinstance(item, dict) or not str(item.get('text', '')).strip():
                raise ProjectError('Invalid target selection item.')
            if int(item.get('occurrence', 0)) < 1 or int(item.get('occurrences', 0)) < 1:
                raise ProjectError('Invalid target selection occurrence metadata.')
        iso, safe = self._timestamp()
        state_root = self.check_dir
        sel_path = state_root / 'selections' / self.book_id / str(chapter) / str(verse) / f'{safe}.json'
        inv_path = state_root / 'invalidated' / self.book_id / str(chapter) / str(verse) / f'{safe}.json'
        tx_paths=[path,sel_path,inv_path]; existed={str(x.resolve()):x.exists() for x in tx_paths}; backup=self._backup_paths(tx_paths, 'checkDataSync')
        journal_tx=self.journal.begin('checkDataSync',tx_paths); self.journal.mark_writing(journal_tx)
        common = {
            'contextId': ctx,
            'modifiedTimestamp': iso,
            'gatewayLanguageCode': gateway_language_code,
            'gatewayLanguageQuote': gateway_language_quote,
            'username': username,
        }
        selection_record = {**common, 'selections': copy.deepcopy(selections), 'nothingToSelect': bool(nothing_to_select)}
        invalid_record = {
            'contextId': ctx, 'username': username, 'invalidated': False,
            'gatewayLanguageCode': gateway_language_code, 'gatewayLanguageQuote': gateway_language_quote,
            'modifiedTimestamp': iso,
        }
        # Persist as one recoverable transaction. If any step fails, restore the pre-write project state.
        try:
            _write_json_atomic(sel_path, selection_record)
            _write_json_atomic(inv_path, invalid_record)
            entry['selections'] = copy.deepcopy(selections)
            entry['nothingToSelect'] = bool(nothing_to_select)
            entry['invalidated'] = False
            data[idx] = entry
            _write_json_atomic(path, data)
        except Exception as e:
            try: self._rollback_paths(backup,tx_paths,existed)
            finally:
                try: self.journal.rollback(journal_tx,str(e))
                except Exception: pass
            self._index_cache.pop(tool,None); raise
        self.journal.commit(journal_tx, {'operation':'checkDataSync','tool':tool,'checkId':check_id})
        self._index_cache.pop(tool, None); self._checks_by_verse_cache = None
        audit = self.companion_dir() / 'audit' / self.book_id / str(chapter) / str(verse) / f'{safe}_tc-sync_{check_id}.json'
        _write_json_atomic(audit, {'operation':'tcCheckApprovalSync','tool':tool,'groupId':group_id,'checkId':check_id,'selections':selections,'nothingToSelect':nothing_to_select,'username':username,'modifiedTimestamp':iso})
        return {'selection': str(sel_path), 'invalidated': str(inv_path), 'index': str(path)}

    def word_alignment_state(self, chapter: str | int, verse: str | int) -> str:
        completed = self.tc_dir / 'tools' / 'wordAlignment' / 'completed' / str(chapter) / f'{verse}.json'
        invalid = self.tc_dir / 'tools' / 'wordAlignment' / 'invalid' / str(chapter) / f'{verse}.json'
        if invalid.exists(): return 'invalid'
        if completed.exists(): return 'completed'
        return 'pending'

    def mark_word_alignment_completed(self, chapter: str | int, verse: str | int, username: str = 'AI Bridge Reviewer') -> Path:
        completed = self.tc_dir / 'tools' / 'wordAlignment' / 'completed' / str(chapter) / f'{verse}.json'
        invalid = self.tc_dir / 'tools' / 'wordAlignment' / 'invalid' / str(chapter) / f'{verse}.json'
        self._backup_paths([completed, invalid], 'wordAlignmentState')
        tx=self.journal.begin('wordAlignmentComplete',[completed,invalid]); self.journal.mark_writing(tx)
        iso, _ = self._timestamp()
        try:
            _write_json_atomic(completed, {'username': username, 'modifiedTimestamp': iso})
            if invalid.exists(): invalid.unlink()
            self.journal.commit(tx,{'operation':'wordAlignmentComplete','chapter':str(chapter),'verse':str(verse)})
        except Exception as e:
            self.journal.rollback(tx,str(e)); raise
        return completed

    def mark_word_alignment_invalid(self, chapter: str | int, verse: str | int) -> Path:
        completed = self.tc_dir / 'tools' / 'wordAlignment' / 'completed' / str(chapter) / f'{verse}.json'
        invalid = self.tc_dir / 'tools' / 'wordAlignment' / 'invalid' / str(chapter) / f'{verse}.json'
        self._backup_paths([completed, invalid], 'wordAlignmentState')
        tx=self.journal.begin('wordAlignmentInvalid',[completed,invalid]); self.journal.mark_writing(tx)
        iso, _ = self._timestamp()
        try:
            _write_json_atomic(invalid, {'timestamp': iso})
            if completed.exists(): completed.unlink()
            self.journal.commit(tx,{'operation':'wordAlignmentInvalid','chapter':str(chapter),'verse':str(verse)})
        except Exception as e:
            self.journal.rollback(tx,str(e)); raise
        return invalid

    @staticmethod
    def _target_tokens(text: str) -> list[dict[str, Any]]:
        words = whitespace_tokens(text)
        totals = Counter(words)
        seen: Counter[str] = Counter()
        out = []
        for word in words:
            seen[word] += 1
            out.append({'word': word, 'occurrence': seen[word], 'occurrences': totals[word], 'type': 'bottomWord'})
        return out

    def _reconcile_alignment_after_target_edit(self, chapter: str | int, verse: str | int, new_text: str) -> dict[str, Any]:
        raw = copy.deepcopy(self.load_alignment_chapter(chapter).get(str(verse), {}))
        self._validate_verse_raw(raw)
        new_tokens = self._target_tokens(new_text)
        new_by_sig = {f"{x['word']}\u241f{x['occurrence']}\u241f{x['occurrences']}": x for x in new_tokens}
        used = set()
        for group in raw['alignments']:
            kept = []
            for token in group.get('bottomWords', []):
                sig = f"{token.get('word','')}\u241f{token.get('occurrence',1)}\u241f{token.get('occurrences',1)}"
                if sig in new_by_sig:
                    kept.append(copy.deepcopy(new_by_sig[sig])); used.add(sig)
            group['bottomWords'] = kept
        bank = []
        for token in new_tokens:
            sig = f"{token['word']}\u241f{token['occurrence']}\u241f{token['occurrences']}"
            if sig not in used:
                bank.append(copy.deepcopy(token)); used.add(sig)
        raw['wordBank'] = bank
        self._validate_verse_raw(raw)
        return raw

    def apply_scripture_edit(self, chapter: str | int, verse: str | int, new_text: str, username: str = 'AI Bridge Reviewer', tags: list[str] | None = None, context_id: dict[str, Any] | None = None) -> dict[str, Any]:
        """Human-only target verse edit with tC-compatible stale propagation and rollback."""
        if str(verse) == 'front':
            raise ProjectError('Front-matter editing is not enabled in v0.6; edit a numbered verse.')
        new_text = str(new_text).strip()
        if not new_text:
            raise ProjectError('Scripture verse may not be empty.')
        chapter_path = self.book_dir / f'{chapter}.json'
        chapter_data = self.target_chapter(chapter)
        old_text = str(chapter_data.get(str(verse), ''))
        if old_text == new_text:
            raise ProjectError('No Scripture text change detected.')
        alignment_path = self.chapter_path(chapter)
        checks = self.checks_for_verse(chapter, verse)
        index_paths: list[Path] = []
        for e in checks:
            tool = str(e.get('contextId', {}).get('tool', '')); gid = str(e.get('contextId', {}).get('groupId', ''))
            ip = self.index_dir / tool / self.book_id / f'{gid}.json'
            if ip.exists() and ip not in index_paths: index_paths.append(ip)
        completed = self.tc_dir / 'tools' / 'wordAlignment' / 'completed' / str(chapter) / f'{verse}.json'
        invalid = self.tc_dir / 'tools' / 'wordAlignment' / 'invalid' / str(chapter) / f'{verse}.json'
        iso, safe = self._timestamp()
        edit_path = self.check_dir / 'verseEdits' / self.book_id / str(chapter) / str(verse) / f'{safe}.json'
        tx_paths=[chapter_path,alignment_path,completed,invalid,edit_path,*index_paths]
        existed={str(x.resolve()):x.exists() for x in tx_paths}
        backup = self._backup_paths(tx_paths, 'scriptureEdit')
        journal_tx=self.journal.begin('scriptureEdit',tx_paths); self.journal.mark_writing(journal_tx)
        new_alignment = self._reconcile_alignment_after_target_edit(chapter, verse, new_text)
        if context_id is None:
            context_id = {'reference': {'bookId': self.book_id, 'chapter': int(chapter) if str(chapter).isdigit() else str(chapter), 'verse': int(verse) if str(verse).isdigit() else str(verse)}, 'tool': 'translationCoreAI', 'groupId': 'human-scripture-edit'}
        edit_record = {
            'verseBefore': old_text, 'verseAfter': new_text, 'tags': list(tags or ['meaning']),
            'username': username, 'activeBook': self.book_id,
            'activeChapter': int(chapter) if str(chapter).isdigit() else str(chapter),
            'activeVerse': int(verse) if str(verse).isdigit() else str(verse),
            'modifiedTimestamp': iso, 'gatewayLanguageCode': 'en', 'gatewayLanguageQuote': '',
            'contextId': copy.deepcopy(context_id),
        }
        touched=[]
        try:
            chapter_data[str(verse)] = new_text
            alignment_chapter = self.load_alignment_chapter(chapter); alignment_chapter[str(verse)] = new_alignment
            _write_json_atomic(chapter_path, chapter_data)
            _write_json_atomic(alignment_path, alignment_chapter)
            # Same mutually-exclusive state observed in the real tC backend.
            _write_json_atomic(invalid, {'timestamp': iso})
            if completed.exists(): completed.unlink()
            _write_json_atomic(edit_path, edit_record)
            # Materialized tC indexes retain selections but flag that a verse edit occurred.
            for ip in index_paths:
                arr = _read_json(ip); changed=False
                if isinstance(arr, list):
                    for e in arr:
                        ref = e.get('contextId', {}).get('reference', {}) if isinstance(e, dict) else {}
                        if str(ref.get('chapter')) == str(chapter) and str(ref.get('verse')) == str(verse):
                            e['verseEdits'] = True; changed=True
                    if changed:
                        _write_json_atomic(ip, arr); touched.append(str(ip))
        except Exception as e:
            try: self._rollback_paths(backup,tx_paths,existed)
            finally:
                try: self.journal.rollback(journal_tx,str(e))
                except Exception: pass
            self._index_cache.clear(); self._checks_by_verse_cache = None; raise
        self.journal.commit(journal_tx,{'operation':'scriptureEdit','chapter':str(chapter),'verse':str(verse)})
        self._index_cache.clear(); self._checks_by_verse_cache = None
        # Companion state is advisory/audit; project transaction is already durable here.
        try:
            review = self.load_review_state(chapter, verse)
            if review and str(review.get('status', '')).lower() in ('approved','human_approved'):
                self.record_review_state(chapter, verse, 'stale_after_verse_edit', note='Scripture text changed; final approval requires recheck.')
            audit = self.companion_dir() / 'audit' / self.book_id / str(chapter) / str(verse) / f'{safe}_scripture-edit.json'
            _write_json_atomic(audit, {'operation':'scriptureEdit','verseBefore':old_text,'verseAfter':new_text,'tags':list(tags or ['meaning']),'username':username,'backup':str(backup),'modifiedTimestamp':iso})
        except Exception:
            pass
        return {'oldText': old_text, 'newText': new_text, 'backup': str(backup), 'verseEdit': str(edit_path), 'alignmentInvalid': str(invalid), 'indexesTouched': touched}

    def record_qa_decision(self, chapter: str | int, verse: str | int, issue_key: str, decision: str, note: str = '', issue: dict[str, Any] | None = None) -> Path:
        iso, safe = self._timestamp()
        key = ''.join(ch if ch.isalnum() or ch in ('-','_') else '_' for ch in issue_key)[:120] or 'qa'
        data = {'bookId':self.book_id,'chapter':str(chapter),'verse':str(verse),'issueKey':issue_key,'decision':decision,'note':note,'issue':copy.deepcopy(issue or {}),'modifiedTimestamp':iso,'app':'translationCore AI Bridge','schemaVersion':1}
        p = self.companion_dir() / 'qaDecisions' / self.book_id / str(chapter) / str(verse) / f'{key}.json'
        _write_json_atomic(p, data)
        audit = self.companion_dir() / 'audit' / self.book_id / str(chapter) / str(verse) / f'{safe}_qa_{key}.json'
        _write_json_atomic(audit, data)
        return p

    def qa_decisions_for_verse(self, chapter: str | int, verse: str | int) -> dict[str, dict[str, Any]]:
        root = self.companion_dir() / 'qaDecisions' / self.book_id / str(chapter) / str(verse)
        out = {}
        if root.exists():
            for p in root.glob('*.json'):
                try:
                    d = _read_json(p)
                    if isinstance(d, dict): out[str(d.get('issueKey',''))] = d
                except Exception: pass
        return out



class TranslationCoreRoot:
    def __init__(self, root: str | Path):
        p = Path(root).resolve()
        # Accept either translationCore root or its parent.
        if (p / 'translationCore' / 'projects').is_dir():
            p = p / 'translationCore'
        if not (p / 'projects').is_dir():
            raise ProjectError(f'Could not find translationCore/projects under {root}')
        self.path = p

    def projects(self) -> list[TranslationCoreProject]:
        out = []
        for p in sorted((self.path / 'projects').iterdir()):
            if p.is_dir() and (p / 'manifest.json').exists():
                try:
                    out.append(TranslationCoreProject(p))
                except ProjectError:
                    pass
        return out
