from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, asdict
from typing import Any

from .alignment_engine import AlignmentError, make_inventory
from .models import VerseAlignment

AUTO_LINK_THRESHOLD = 0.72
REVIEW_LINK_THRESHOLD = 0.45
COMPILER_VERSION = '0.7.4'


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def alignment_fingerprint(alignment: VerseAlignment) -> str:
    return _json_hash(alignment.to_dict())


def source_token_fingerprint(alignment: VerseAlignment) -> str:
    inv = make_inventory(alignment)
    return _json_hash([
        {
            'word': t.word,
            'occurrence': t.occurrence,
            'occurrences': t.occurrences,
            'strong': t.strong,
            'lemma': t.lemma,
            'morph': t.morph,
        }
        for t in inv.top
    ])


def target_token_fingerprint(alignment: VerseAlignment, target_text: str = '') -> str:
    inv = make_inventory(alignment)
    return _json_hash({
        'text': target_text,
        'tokens': [
            {'word': t.word, 'occurrence': t.occurrence, 'occurrences': t.occurrences}
            for t in inv.bottom
        ],
    })


@dataclass(frozen=True)
class AIRequestContext:
    request_id: str
    project_path: str
    book_id: str
    chapter: str
    verse: str
    source_fingerprint: str
    target_fingerprint: str
    alignment_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_request_context(project, chapter: str, verse: str, alignment: VerseAlignment) -> AIRequestContext:
    return AIRequestContext(
        request_id=uuid.uuid4().hex,
        project_path=str(project.path),
        book_id=str(project.book_id).lower(),
        chapter=str(chapter),
        verse=str(verse),
        source_fingerprint=source_token_fingerprint(alignment),
        target_fingerprint=target_token_fingerprint(alignment, project.target_verse_text(chapter, verse)),
        alignment_fingerprint=alignment_fingerprint(alignment),
    )


def request_context_matches(context: AIRequestContext, project, chapter: str, verse: str, alignment: VerseAlignment) -> bool:
    if str(project.path) != context.project_path:
        return False
    if str(project.book_id).lower() != context.book_id:
        return False
    if str(chapter) != context.chapter or str(verse) != context.verse:
        return False
    return (
        source_token_fingerprint(alignment) == context.source_fingerprint
        and target_token_fingerprint(alignment, project.target_verse_text(chapter, verse)) == context.target_fingerprint
        and alignment_fingerprint(alignment) == context.alignment_fingerprint
    )


def structural_issues(alignment: VerseAlignment) -> list[str]:
    """Return deterministic structural issues without changing the alignment."""
    issues: list[str] = []
    seen_top: dict[str, int] = {}
    seen_bottom: dict[str, str] = {}
    for gi, group in enumerate(alignment.alignments, 1):
        if not group.top_words and group.bottom_words:
            issues.append(f'group {gi} has target tokens but no source tokens')
        for token in group.top_words:
            if token.signature in seen_top:
                issues.append(f'source token {token.word!r} occurs in groups {seen_top[token.signature]} and {gi}')
            else:
                seen_top[token.signature] = gi
        for token in group.bottom_words:
            if token.signature in seen_bottom:
                issues.append(f'target token {token.word!r} occurs more than once ({seen_bottom[token.signature]} and group {gi})')
            else:
                seen_bottom[token.signature] = f'group {gi}'
    for token in alignment.word_bank:
        if token.signature in seen_bottom:
            issues.append(f'target token {token.word!r} occurs in {seen_bottom[token.signature]} and wordBank')
        else:
            seen_bottom[token.signature] = 'wordBank'
    return issues


def _legacy_groups_to_links(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str], list[str]]:
    links: list[dict[str, Any]] = []
    implicit: set[str] = set()
    notes = [str(x) for x in raw.get('review_notes', []) if isinstance(x, (str, int, float))]
    groups = raw.get('groups')
    if not isinstance(groups, list):
        return links, implicit, notes
    for group in groups:
        if not isinstance(group, dict):
            continue
        tops = group.get('top_ids', [])
        bottoms = group.get('bottom_ids', [])
        if not isinstance(tops, list) or not isinstance(bottoms, list):
            continue
        confidence = float(group.get('confidence', 0) or 0)
        reason = str(group.get('reason', '') or '')
        if not bottoms:
            implicit.update(str(x) for x in tops)
            continue
        for top_id in tops:
            for bottom_id in bottoms:
                links.append({
                    'top_id': str(top_id),
                    'bottom_id': str(bottom_id),
                    'confidence': confidence,
                    'reason': reason,
                })
    return links, implicit, notes


def normalize_link_response(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str], list[str]]:
    """Normalize new link schema and legacy group schema for backwards-compatible tests/caches."""
    if not isinstance(raw, dict):
        raise AlignmentError('AI alignment response is not an object.')
    if isinstance(raw.get('links'), list):
        links: list[dict[str, Any]] = []
        for i, item in enumerate(raw['links'], 1):
            if not isinstance(item, dict):
                raise AlignmentError(f'AI alignment link {i} is not an object.')
            top_id = str(item.get('top_id', '') or '')
            bottom_id = str(item.get('bottom_id', '') or '')
            if not top_id or not bottom_id:
                raise AlignmentError(f'AI alignment link {i} must contain top_id and bottom_id.')
            links.append({
                'top_id': top_id,
                'bottom_id': bottom_id,
                'confidence': float(item.get('confidence', 0) or 0),
                'reason': str(item.get('reason', '') or ''),
            })
        implicit = {str(x) for x in raw.get('implicit_top_ids', []) if str(x)} if isinstance(raw.get('implicit_top_ids'), list) else set()
        notes = [str(x) for x in raw.get('review_notes', [])] if isinstance(raw.get('review_notes'), list) else []
        return links, implicit, notes
    if isinstance(raw.get('groups'), list):
        return _legacy_groups_to_links(raw)
    raise AlignmentError('AI alignment response has neither links nor legacy groups.')


def _id_sort(value: str) -> tuple[str, int, str]:
    prefix = value[:1]
    try:
        num = int(value[1:])
    except Exception:
        num = 10**9
    return prefix, num, value


def _existing_protected_groups(alignment: VerseAlignment, inv) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for group in alignment.alignments:
        if not group.top_words or not group.bottom_words:
            continue
        top_ids = [inv.top_sig_to_id[x.signature] for x in group.top_words if x.signature in inv.top_sig_to_id]
        bottom_ids = [inv.bottom_sig_to_id[x.signature] for x in group.bottom_words if x.signature in inv.bottom_sig_to_id]
        if top_ids and bottom_ids:
            groups.append({
                'top_ids': sorted(top_ids, key=_id_sort),
                'bottom_ids': sorted(bottom_ids, key=_id_sort),
                'confidence': 1.0,
                'reason': 'Protected existing project alignment.',
                'origin': 'existing',
            })
    return groups


def compile_link_proposal(
    alignment: VerseAlignment,
    raw_response: dict[str, Any],
    *,
    mode: str = 'gap_fill',
    auto_threshold: float = AUTO_LINK_THRESHOLD,
    review_threshold: float = REVIEW_LINK_THRESHOLD,
    lock_policy: str = 'protected',
) -> dict[str, Any]:
    """Compile AI linguistic links into deterministic legal translationCore groups.

    gap_fill preserves existing non-empty top↔bottom groups. Protected legacy/partial groups may
    be extended only as an unsaved proposal when one endpoint is unresolved; human-approved hard
    locks cannot be extended. Any bridge between established groups is blocked. audit/whole builds
    a read-only candidate from all tokens and does not grant protection to existing groups.
    """
    if mode not in ('gap_fill', 'audit', 'whole'):
        raise AlignmentError(f'Unknown alignment compiler mode: {mode}')
    if lock_policy not in ('protected','hard'):
        raise AlignmentError(f'Unknown alignment lock policy: {lock_policy}')
    inv = make_inventory(alignment)
    links, implicit_top_ids, review_notes = normalize_link_response(raw_response)
    target_only_ids = {str(x) for x in raw_response.get('target_only_ids', []) if str(x)} if isinstance(raw_response.get('target_only_ids'), list) else set()
    for target_id in target_only_ids:
        if target_id not in inv.bottom_ids:
            raise AlignmentError(f'AI returned unknown target-only token id: {target_id}')

    protected = _existing_protected_groups(alignment, inv) if mode == 'gap_fill' else []
    locked_top: dict[str, int] = {}
    locked_bottom: dict[str, int] = {}
    for idx, group in enumerate(protected):
        for tid in group['top_ids']:
            locked_top[tid] = idx
        for tid in group['bottom_ids']:
            locked_bottom[tid] = idx

    diagnostics: list[dict[str, Any]] = []
    for target_id in sorted(target_only_ids, key=_id_sort):
        diagnostics.append({'type':'target_only_candidate','bottom_id':target_id,'action':'kept_unaligned_for_human_review'})
    conflicts: list[dict[str, Any]] = []
    accepted_links: list[dict[str, Any]] = []
    uncertain_links: list[dict[str, Any]] = []
    seen_link_keys: set[tuple[str, str]] = set()

    for i, link in enumerate(links, 1):
        top_id = link['top_id']; bottom_id = link['bottom_id']
        if top_id not in inv.top_ids:
            raise AlignmentError(f'AI returned unknown source token id: {top_id}')
        if bottom_id not in inv.bottom_ids:
            raise AlignmentError(f'AI returned unknown target token id: {bottom_id}')
        key = (top_id, bottom_id)
        if key in seen_link_keys:
            diagnostics.append({'type': 'duplicate_link', 'top_id': top_id, 'bottom_id': bottom_id, 'action': 'deduplicated'})
            continue
        seen_link_keys.add(key)
        confidence = max(0.0, min(1.0, float(link.get('confidence', 0) or 0)))
        normalized = {**link, 'confidence': confidence}

        if mode == 'gap_fill' and (top_id in locked_top or bottom_id in locked_bottom):
            top_group = locked_top.get(top_id)
            bottom_group = locked_bottom.get(bottom_id)
            if top_group is not None and top_group == bottom_group:
                diagnostics.append({'type': 'restates_protected', 'top_id': top_id, 'bottom_id': bottom_id, 'action': 'ignored'})
                continue
            # Connecting two different protected groups is never auto-normalized. A single
            # protected endpoint may be extended only for legacy/partial work and still requires
            # explicit human Apply+Save; a human-approved verse uses hard lock policy.
            if (top_group is not None and bottom_group is not None and top_group != bottom_group) or lock_policy == 'hard':
                conflict = {
                    'type': 'protected_alignment_conflict', 'top_id': top_id, 'bottom_id': bottom_id,
                    'confidence': confidence, 'reason': str(link.get('reason', '') or ''), 'action': 'not_applied',
                }
                conflicts.append(conflict); diagnostics.append(conflict); continue
            normalized['protected_anchor'] = top_group if top_group is not None else bottom_group

        if confidence >= auto_threshold:
            accepted_links.append(normalized)
        elif confidence >= review_threshold:
            uncertain_links.append(normalized)
            diagnostics.append({
                'type': 'uncertain_link', 'top_id': top_id, 'bottom_id': bottom_id,
                'confidence': confidence, 'action': 'not_auto_merged',
            })
        else:
            diagnostics.append({
                'type': 'low_confidence_link', 'top_id': top_id, 'bottom_id': bottom_id,
                'confidence': confidence, 'action': 'ignored',
            })

    # Build connected components only from strong/accepted edges. This prevents one weak bridge
    # from collapsing independent groups into a huge many-to-many component.
    adjacency: dict[str, set[str]] = {}
    edge_map: dict[frozenset[str], list[dict[str, Any]]] = {}
    for link in accepted_links:
        h = 'H:' + link['top_id']; t = 'T:' + link['bottom_id']
        adjacency.setdefault(h, set()).add(t); adjacency.setdefault(t, set()).add(h)
        edge_map.setdefault(frozenset((h, t)), []).append(link)

    components: list[set[str]] = []
    visited: set[str] = set()
    for node in sorted(adjacency):
        if node in visited:
            continue
        stack = [node]; comp: set[str] = set(); visited.add(node)
        while stack:
            cur = stack.pop(); comp.add(cur)
            for nxt in sorted(adjacency.get(cur, ())):
                if nxt not in visited:
                    visited.add(nxt); stack.append(nxt)
        components.append(comp)

    compiled_groups: list[dict[str, Any]] = []
    used_top: set[str] = set(); used_bottom: set[str] = set(); extended_protected: set[int] = set()
    for comp in components:
        top_ids = sorted((x[2:] for x in comp if x.startswith('H:')), key=_id_sort)
        bottom_ids = sorted((x[2:] for x in comp if x.startswith('T:')), key=_id_sort)
        if not top_ids or not bottom_ids:
            continue
        comp_edges = [x for x in accepted_links if x['top_id'] in top_ids and x['bottom_id'] in bottom_ids]
        anchors={locked_top[x] for x in top_ids if x in locked_top} | {locked_bottom[x] for x in bottom_ids if x in locked_bottom}
        if len(anchors) > 1:
            conflict={'type':'protected_component_bridge','top_ids':top_ids,'bottom_ids':bottom_ids,'action':'not_applied'}
            conflicts.append(conflict); diagnostics.append(conflict)
            continue
        if anchors:
            anchor=next(iter(anchors)); base=protected[anchor]
            top_ids=sorted(set(top_ids) | set(base['top_ids']), key=_id_sort)
            bottom_ids=sorted(set(bottom_ids) | set(base['bottom_ids']), key=_id_sort)
            extended_protected.add(anchor)
        confidence = min((float(x.get('confidence', 0) or 0) for x in comp_edges), default=0.0)
        reasons: list[str] = []
        for edge in comp_edges:
            reason = str(edge.get('reason', '') or '').strip()
            if reason and reason not in reasons: reasons.append(reason)
        relation = 'one-to-one'
        if len(top_ids) > 1 and len(bottom_ids) == 1: relation = 'many-to-one'
        elif len(top_ids) == 1 and len(bottom_ids) > 1: relation = 'one-to-many'
        elif len(top_ids) > 1 and len(bottom_ids) > 1: relation = 'many-to-many'
        origin='extended_protected' if anchors else 'ai_compiled'
        compiled_groups.append({
            'top_ids': top_ids, 'bottom_ids': bottom_ids, 'confidence': confidence,
            'reason': '; '.join(reasons) or f'Deterministically compiled {relation} relationship.',
            'origin': origin, 'relation': relation,
        })
        used_top.update(x for x in top_ids if x not in locked_top)
        used_bottom.update(x for x in bottom_ids if x not in locked_bottom)

    if extended_protected:
        diagnostics.append({'type':'protected_extension','groups':sorted(extended_protected),'action':'compiled_for_explicit_human_review'})
    protected_kept=[g for i,g in enumerate(protected) if i not in extended_protected]

    all_top = set(inv.top_ids)
    all_bottom = set(inv.bottom_ids)
    if mode == 'gap_fill':
        open_top = all_top - set(locked_top)
        open_bottom = all_bottom - set(locked_bottom)
    else:
        open_top = all_top
        open_bottom = all_bottom

    # Preserve source coverage. An empty bottom list is legal tC representation for an unresolved
    # or implicit source token. Companion diagnostics retain the distinction when AI explicitly
    # marks it implicit.
    empty_top_groups: list[dict[str, Any]] = []
    for top_id in sorted(open_top - used_top, key=_id_sort):
        is_implicit = top_id in implicit_top_ids
        empty_top_groups.append({
            'top_ids': [top_id],
            'bottom_ids': [],
            'confidence': 1.0 if is_implicit else 0.0,
            'reason': 'Source meaning represented implicitly; no separate target token.' if is_implicit else 'No high-confidence target link was compiled.',
            'origin': 'implicit' if is_implicit else 'unresolved',
            'relation': 'implicit' if is_implicit else 'unresolved',
        })

    groups = [*protected_kept, *compiled_groups, *empty_top_groups]
    groups.sort(key=lambda g: min((_id_sort(x) for x in g.get('top_ids', [])), default=('Z', 10**9, '')))

    notes = list(review_notes)
    if target_only_ids:
        notes.append(f'{len(target_only_ids)} target token(s) were marked as target-language grammatical/natural expression with no separate source token; they remain unaligned for explicit human review.')
    if uncertain_links:
        notes.append(f'{len(uncertain_links)} medium-confidence link(s) were kept out of automatic grouping for human review.')
    if conflicts:
        notes.append(f'{len(conflicts)} AI link(s) conflicted with protected existing alignment and were not applied.')
    low_count = sum(1 for d in diagnostics if d.get('type') == 'low_confidence_link')
    if low_count:
        notes.append(f'{low_count} low-confidence link(s) were ignored by the deterministic compiler.')

    return {
        'groups': groups,
        'links': accepted_links,
        'uncertain_links': uncertain_links,
        'implicit_top_ids': sorted(implicit_top_ids, key=_id_sort),
        'target_only_ids': sorted(target_only_ids, key=_id_sort),
        'review_notes': notes,
        'diagnostics': diagnostics,
        'conflicts': conflicts,
        'requires_human_review': bool(conflicts or uncertain_links or target_only_ids),
        'compiler_version': COMPILER_VERSION,
        'mode': mode,
        'lock_policy': lock_policy,
        'thresholds': {'auto': auto_threshold, 'review': review_threshold},
    }


def proposal_difference(alignment: VerseAlignment, proposal: dict[str, Any]) -> dict[str, Any]:
    """Compare group memberships order-insensitively for a read-only audit summary."""
    inv = make_inventory(alignment)
    existing = {
        (tuple(sorted((inv.top_sig_to_id[x.signature] for x in g.top_words if x.signature in inv.top_sig_to_id), key=_id_sort)),
         tuple(sorted((inv.bottom_sig_to_id[x.signature] for x in g.bottom_words if x.signature in inv.bottom_sig_to_id), key=_id_sort)))
        for g in alignment.alignments if g.top_words
    }
    proposed = {
        (tuple(sorted((str(x) for x in g.get('top_ids', [])), key=_id_sort)),
         tuple(sorted((str(x) for x in g.get('bottom_ids', [])), key=_id_sort)))
        for g in proposal.get('groups', []) if isinstance(g, dict) and g.get('top_ids')
    }
    return {
        'unchanged': len(existing & proposed),
        'existing_only': sorted(existing - proposed),
        'proposal_only': sorted(proposed - existing),
        'changed': bool(existing != proposed),
    }
