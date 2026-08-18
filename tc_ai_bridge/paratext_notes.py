from __future__ import annotations

import os
import re
import tempfile
import uuid
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


class ParatextNoteError(RuntimeError):
    pass


EXTERNAL_NOTE_SOURCE = 'AI Suggestion'


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _iso_paratext_date() -> str:
    """Return an offset-aware timestamp accepted by the Paratext Notes 1.1 schema."""
    now = datetime.now().astimezone()
    base = now.strftime('%Y-%m-%dT%H:%M:%S.%f') + '0'
    offset = now.strftime('%z')
    if len(offset) == 5:
        offset = offset[:3] + ':' + offset[3:]
    return base + offset


def _atomic_write_xml(path: Path, root: ET.Element) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space='  ')
    tree = ET.ElementTree(root)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    os.close(fd)
    try:
        tree.write(tmp, encoding='utf-8', xml_declaration=True, short_empty_elements=True)
        ET.parse(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _verse_snapshot(verse: str | int, verse_text: str) -> str:
    """Build the same USFM-like snapshot used by the supplied Paratext CommentList export."""
    raw = str(verse_text or '')
    stripped = raw.lstrip()
    if stripped.startswith('\\v ') or stripped.startswith('\\id '):
        return raw
    return f'\\v {verse} {raw}' if raw else f'\\v {verse} '


def _selection_context(verse_snapshot: str, selected_text: str, radius: int = 55) -> tuple[str, int, str, str]:
    selected = str(selected_text or '').strip()
    start = verse_snapshot.find(selected) if selected else -1
    if start < 0 and selected:
        # TN/TW selections can be discontinuous or can be reconstructed from token records with
        # spaces that do not exactly match punctuation in the verse. Paratext can attach a note to
        # only one contiguous range. Prefer the longest *exact* contiguous token subsequence rather
        # than inventing an offset. This makes the note icon land on real target text.
        parts = selected.split()
        best = ''
        best_start = -1
        for width in range(len(parts), 0, -1):
            for i in range(0, len(parts) - width + 1):
                candidate = ' '.join(parts[i:i + width])
                pos = verse_snapshot.find(candidate)
                if pos >= 0 and len(candidate) > len(best):
                    best, best_start = candidate, pos
            if best:
                break
        selected, start = best, best_start
    if start < 0:
        # For verse-level QA notes attach to the target verse text (excluding the USFM marker) so
        # Paratext can show an icon at the verse instead of an unattached/false character offset.
        marker_end = verse_snapshot.find(' ')
        marker_end = verse_snapshot.find(' ', marker_end + 1) if marker_end >= 0 else -1
        selected = verse_snapshot[marker_end + 1:].strip() if marker_end >= 0 else verse_snapshot.strip()
        start = verse_snapshot.find(selected) if selected else 0
    before = verse_snapshot[max(0, start - radius):start]
    after_start = start + len(selected)
    after = verse_snapshot[after_start:after_start + radius]
    return selected, start, before, after


# ---------------------------------------------------------------------------
# Official Paratext Notes 1.1 format (Data Access notes schema)
# ---------------------------------------------------------------------------

def load_or_create_notes_11(path: str | Path) -> ET.Element:
    p = Path(path)
    if p.exists():
        root = ET.parse(p).getroot()
        if root.tag != 'notes':
            raise ParatextNoteError(f'Expected Paratext Notes 1.1 <notes> XML: {p}')
        if not str(root.attrib.get('version', '')).startswith('1.1'):
            raise ParatextNoteError(f'Unsupported Paratext notes version: {root.attrib.get("version")}')
        return root
    return ET.Element('notes', {'version': '1.1'})


def append_paratext_note(
    path: str | Path,
    *,
    book_id: str,
    chapter: str | int,
    verse: str | int,
    verse_text: str,
    comment_text: str,
    reviewer: str,
    selected_text: str = '',
    language: str = '',  # retained for API compatibility; language belongs to the project, not Notes 1.1
    thread_id: str | None = None,
    status: str = '',  # retained for call compatibility; Notes 1.1 has no status attribute
    note_type: str = '',
    conflict_type: str = '',
    assigned_user: str = '',
    reply_to_user: str = '',
    hide_in_text_window: bool = False,
    metadata: dict[str, Any] | None = None,
    ext_user: str = EXTERNAL_NOTE_SOURCE,
) -> tuple[Path, str]:
    """Append one API-ready Paratext Notes 1.1 project note.

    ``reviewer`` is stored as an author hint in the Bridge companion. Before an API-ready XML
    export, it is normalized to the detected/configured real Paratext project member. Live Plugin
    API synchronization lets Paratext assign the current logged-in user itself. ``ext_user``
    records the external AI origin without inventing a Paratext project member.

    The selection is attached to the exact selected text when it occurs in the current verse
    snapshot. If it does not, the note is safely downgraded to a verse-level selection rather than
    storing a false offset.
    """
    p = Path(path)
    content = str(comment_text or '').strip()
    if not content:
        raise ParatextNoteError('Paratext reviewer note text may not be empty.')
    user = str(reviewer or '').strip()
    if not user:
        raise ParatextNoteError('A non-empty reviewer/author hint is required for the Bridge Notes 1.1 companion.')

    snapshot = _verse_snapshot(verse, verse_text)
    selected, start, before, after = _selection_context(snapshot, selected_text)
    tid = str(thread_id or uuid.uuid4().hex)
    root = load_or_create_notes_11(p)
    thread_attrs = {'id': tid}
    if note_type:
        thread_attrs['type'] = str(note_type)
    thread = ET.SubElement(root, 'thread', thread_attrs)
    ET.SubElement(thread, 'selection', {
        'verseRef': f'{str(book_id).upper()} {chapter}:{verse}',
        'startPos': str(start),
        'selectedText': selected,
        'beforeContext': before,
        'afterContext': after,
    })
    comment_attrs = {'user': user, 'date': _iso_paratext_date()}
    if str(ext_user or '').strip():
        comment_attrs['extUser'] = str(ext_user).strip()
    comment = ET.SubElement(thread, 'comment', comment_attrs)
    ET.SubElement(comment, 'content').text = content
    _atomic_write_xml(p, root)
    return p, tid


_DATE_RE = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{5,}[+-]\d\d:\d\d$')


def validate_notes_11(path: str | Path) -> dict[str, Any]:
    """Validate the Notes 1.1 subset generated by the Bridge against the official schema shape."""
    p = Path(path)
    root = ET.parse(p).getroot()
    if root.tag != 'notes' or not str(root.attrib.get('version', '')).startswith('1.1'):
        raise ParatextNoteError('Expected <notes version="1.1">.')
    threads = list(root.findall('thread'))
    comments = 0
    for thread in threads:
        if 'id' not in thread.attrib:
            raise ParatextNoteError('Each Paratext note thread requires an id.')
        selection = thread.find('selection')
        if selection is None:
            raise ParatextNoteError('Each Paratext note thread requires a selection.')
        for attr in ('verseRef', 'startPos', 'selectedText'):
            if attr not in selection.attrib:
                raise ParatextNoteError(f'Paratext selection requires {attr}.')
        try:
            int(selection.attrib['startPos'])
        except Exception as e:
            raise ParatextNoteError('Paratext selection startPos must be an integer.') from e
        cs = list(thread.findall('comment'))
        if not cs:
            raise ParatextNoteError('Each Paratext note thread requires at least one comment.')
        for c in cs:
            if not c.attrib.get('user') or not _DATE_RE.match(str(c.attrib.get('date', ''))):
                raise ParatextNoteError('Paratext comment requires user and offset-aware date.')
            if c.find('content') is None:
                raise ParatextNoteError('Paratext comment requires <content>.')
        comments += len(cs)
    return {'format': 'Paratext Notes 1.1', 'threads': len(threads), 'comments': comments, 'path': str(p)}


def normalized_notes_11_copy(
    src: str | Path,
    dst: str | Path,
    *,
    paratext_user: str,
    ext_user: str = EXTERNAL_NOTE_SOURCE,
) -> Path:
    """Write a safe Notes 1.1 copy using a real Paratext user as comment author.

    Paratext Data Access requires ``comment@user`` to identify a real project member (except
    administrators posting for another project member). AI provenance belongs in ``extUser``.
    This function deliberately does not modify the Bridge companion source file.
    """
    sp, dp = Path(src), Path(dst)
    try:
        if sp.resolve() == dp.resolve():
            raise ParatextNoteError('Choose a different export destination; the Bridge companion Notes file is preserved as source data.')
    except FileNotFoundError:
        pass
    user = str(paratext_user or '').strip()
    if not user:
        raise ParatextNoteError('A real Paratext user is required to export API-ready Notes 1.1 XML.')
    root = ET.parse(sp).getroot()
    if root.tag != 'notes' or not str(root.attrib.get('version', '')).startswith('1.1'):
        raise ParatextNoteError('Expected Paratext Notes 1.1 XML.')
    for comment in root.findall('.//comment'):
        comment.attrib['user'] = user
        if str(ext_user or '').strip():
            comment.attrib['extUser'] = str(ext_user).strip()
        else:
            comment.attrib.pop('extUser', None)
    _atomic_write_xml(dp, root)
    validate_notes_11(dp)
    return dp


def iter_notes_11(path: str | Path) -> list[dict[str, Any]]:
    """Return Bridge Notes 1.1 threads in a connector-friendly, deterministic shape.

    The Bridge currently creates one comment per thread. If an imported/edited thread contains
    multiple comments, it is returned with ``unsupported_reason`` so batch live sync fails closed
    instead of flattening a Paratext discussion into a new note.
    """
    p = Path(path)
    validate_notes_11(p)
    root = ET.parse(p).getroot()
    out: list[dict[str, Any]] = []
    for thread in root.findall('thread'):
        tid = str(thread.attrib.get('id') or '').strip()
        selection = thread.find('selection')
        comments = thread.findall('comment')
        item: dict[str, Any] = {
            'thread_id': tid,
            'reference': str(selection.attrib.get('verseRef') or '').strip().upper() if selection is not None else '',
            'selected_text': str(selection.attrib.get('selectedText') or '') if selection is not None else '',
            'before_context': str(selection.attrib.get('beforeContext') or '') if selection is not None else '',
            'after_context': str(selection.attrib.get('afterContext') or '') if selection is not None else '',
            'user': '',
            'external_author': '',
            'content': '',
            'unsupported_reason': '',
        }
        if len(comments) != 1:
            item['unsupported_reason'] = f'Thread contains {len(comments)} comments; live batch sync supports one Bridge comment per thread.'
        elif comments:
            comment = comments[0]
            item['user'] = str(comment.attrib.get('user') or '').strip()
            item['external_author'] = str(comment.attrib.get('extUser') or '').strip()
            item['content'] = str(comment.findtext('content') or '').strip()
            if not item['content']:
                item['unsupported_reason'] = 'Note content is empty.'
        if not item['reference']:
            item['unsupported_reason'] = item['unsupported_reason'] or 'Scripture reference is missing.'
        canonical = {k: item[k] for k in ('thread_id','reference','selected_text','before_context','after_context','content')}
        item['fingerprint'] = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# User-supplied CommentList export format
# ---------------------------------------------------------------------------
# This format is useful for round-tripping/reporting the sample supplied by the user, but it is
# *not* used as the primary Paratext project-note sync payload. The official Data Access endpoint
# accepts Notes 1.1 above.
COMMENT_CHILD_ORDER = (
    'SelectedText', 'StartPosition', 'ContextBefore', 'ContextAfter',
    'Status', 'Type', 'ConflictType', 'Verse',
    'AssignedUser', 'ReplyToUser', 'HideInTextWindow', 'Contents',
    'TagAdded', 'TagRemoved',
)
REQUIRED_COMMENT_ATTRS = ('Thread', 'User', 'VerseRef', 'Language', 'Date')
REQUIRED_COMMENT_CHILDREN = (
    'SelectedText', 'StartPosition', 'ContextBefore', 'ContextAfter',
    'Status', 'Type', 'ConflictType', 'Verse', 'HideInTextWindow',
)


def validate_comment_list(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    root = ET.parse(p).getroot()
    if root.tag != 'CommentList':
        raise ParatextNoteError('Expected <CommentList>.')
    comments = list(root.findall('Comment'))
    for c in comments:
        for attr in REQUIRED_COMMENT_ATTRS:
            if attr not in c.attrib:
                raise ParatextNoteError(f'Comment attribute {attr} is required.')
        for tag in REQUIRED_COMMENT_CHILDREN:
            if c.find(tag) is None:
                raise ParatextNoteError(f'Comment element <{tag}> is required.')
        int(c.findtext('StartPosition') or '0')
        child_names = [x.tag for x in c]
        order = {name: i for i, name in enumerate(COMMENT_CHILD_ORDER)}
        seen = [order[x] for x in child_names if x in order]
        if seen != sorted(seen):
            raise ParatextNoteError('Comment child elements are not in Paratext export order.')
    return {'format': 'CommentList', 'comments': len(comments), 'path': str(p)}


def convert_comment_list_to_notes_11(src: str | Path, dst: str | Path, *, ext_user: str = EXTERNAL_NOTE_SOURCE) -> Path:
    """Migrate v0.7.1/user-export CommentList records into API-ready Notes 1.1."""
    sp, dp = Path(src), Path(dst)
    root = ET.parse(sp).getroot()
    if root.tag != 'CommentList':
        raise ParatextNoteError(f'Not a CommentList file: {sp}')
    out = ET.Element('notes', {'version': '1.1'})
    for old in root.findall('Comment'):
        thread = ET.SubElement(out, 'thread', {'id': str(old.attrib.get('Thread') or uuid.uuid4().hex)})
        ET.SubElement(thread, 'selection', {
            'verseRef': str(old.attrib.get('VerseRef') or ''),
            'startPos': str(old.findtext('StartPosition') or '0'),
            'selectedText': str(old.findtext('SelectedText') or ''),
            'beforeContext': str(old.findtext('ContextBefore') or ''),
            'afterContext': str(old.findtext('ContextAfter') or ''),
        })
        attrs = {
            'user': str(old.attrib.get('User') or 'AI Bridge Reviewer'),
            'date': str(old.attrib.get('Date') or _iso_paratext_date()),
        }
        if ext_user:
            attrs['extUser'] = ext_user
        comment = ET.SubElement(thread, 'comment', attrs)
        ET.SubElement(comment, 'content').text = str(old.findtext('Contents') or '')
    _atomic_write_xml(dp, out)
    return dp


def export_notes_11_as_comment_list(
    src: str | Path,
    dst: str | Path,
    *,
    language: str = 'und',
    verse_snapshot_lookup: Callable[[str], str] | None = None,
) -> Path:
    """Create a CommentList-style report matching the supplied export structure.

    This is retained for comparison/interchange with the user's supplied sample. It is separate
    from the official Notes 1.1 sync payload.
    """
    sp, dp = Path(src), Path(dst)
    root = ET.parse(sp).getroot()
    if root.tag != 'notes':
        raise ParatextNoteError(f'Not a Notes 1.1 file: {sp}')
    out = ET.Element('CommentList')
    for thread in root.findall('thread'):
        sel = thread.find('selection')
        if sel is None:
            continue
        verse_ref = sel.attrib.get('verseRef', '')
        snapshot = verse_snapshot_lookup(verse_ref) if verse_snapshot_lookup else ''
        for old in thread.findall('comment'):
            c = ET.SubElement(out, 'Comment', {
                'Thread': str(thread.attrib.get('id') or uuid.uuid4().hex[:8])[:8],
                'User': str(old.attrib.get('user') or ''),
                'VerseRef': verse_ref,
                'Language': language or 'und',
                'Date': str(old.attrib.get('date') or _iso_paratext_date()),
            })
            ET.SubElement(c, 'SelectedText').text = sel.attrib.get('selectedText', '')
            ET.SubElement(c, 'StartPosition').text = sel.attrib.get('startPos', '0')
            ET.SubElement(c, 'ContextBefore').text = sel.attrib.get('beforeContext', '')
            ET.SubElement(c, 'ContextAfter').text = sel.attrib.get('afterContext', '')
            ET.SubElement(c, 'Status').text = ''
            ET.SubElement(c, 'Type').text = ''
            ET.SubElement(c, 'ConflictType').text = 'unknownConflictType'
            ET.SubElement(c, 'Verse').text = snapshot
            ET.SubElement(c, 'ReplyToUser').text = ''
            ET.SubElement(c, 'HideInTextWindow').text = 'false'
            content = old.find('content')
            ET.SubElement(c, 'Contents').text = ''.join(content.itertext()).strip() if content is not None else ''
    _atomic_write_xml(dp, out)
    return dp


# Compatibility alias retained for extensions written against v0.7.1 naming.
def convert_legacy_notes_11(src: str | Path, dst: str | Path, *, language: str = 'und') -> Path:
    # In v0.7.1 this name meant Notes1.1 -> CommentList. The corrected migration direction is now
    # CommentList -> Notes1.1; accept either shape so upgrades never discard data.
    root = ET.parse(src).getroot()
    if root.tag == 'CommentList':
        return convert_comment_list_to_notes_11(src, dst)
    if root.tag == 'notes':
        # Already official: copy atomically into destination.
        _atomic_write_xml(Path(dst), root)
        return Path(dst)
    raise ParatextNoteError(f'Unsupported legacy notes XML: {src}')
