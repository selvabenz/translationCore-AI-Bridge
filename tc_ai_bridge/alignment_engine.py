from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .models import AlignmentGroup, TokenRef, VerseAlignment


class AlignmentError(ValueError):
    pass


@dataclass
class TokenInventory:
    top: list[TokenRef]
    bottom: list[TokenRef]
    top_ids: dict[str, TokenRef]
    bottom_ids: dict[str, TokenRef]
    top_sig_to_id: dict[str, str]
    bottom_sig_to_id: dict[str, str]


def make_inventory(verse: VerseAlignment) -> TokenInventory:
    # translationCore represents each source token once among alignment groups. Keep its
    # original group order. Target tokens are assembled from aligned groups + wordBank.
    top: list[TokenRef] = []
    bottom: list[TokenRef] = []
    seen_top: set[str] = set()
    seen_bottom: set[str] = set()
    for group in verse.alignments:
        for token in group.top_words:
            if token.signature not in seen_top:
                top.append(token); seen_top.add(token.signature)
        for token in group.bottom_words:
            if token.signature not in seen_bottom:
                bottom.append(token); seen_bottom.add(token.signature)
    for token in verse.word_bank:
        if token.signature not in seen_bottom:
            bottom.append(token); seen_bottom.add(token.signature)
    top_ids = {f'H{i:03d}': t for i, t in enumerate(top, 1)}
    bottom_ids = {f'T{i:03d}': t for i, t in enumerate(bottom, 1)}
    return TokenInventory(
        top, bottom, top_ids, bottom_ids,
        {t.signature: i for i, t in top_ids.items()},
        {t.signature: i for i, t in bottom_ids.items()},
    )


def token_label(token: TokenRef, include_morph: bool = False) -> str:
    label = f'{token.word}  [{token.occurrence}/{token.occurrences}]'
    if include_morph and (token.lemma or token.morph):
        label += f'  {token.lemma} {token.morph}'.rstrip()
    return label


def realign(verse: VerseAlignment, selected_top: list[TokenRef], selected_bottom: list[TokenRef]) -> VerseAlignment:
    if not selected_top:
        raise AlignmentError('Select at least one source-language topWord.')
    if not selected_bottom:
        raise AlignmentError('Select at least one target-language bottomWord.')
    top_sigs = {x.signature for x in selected_top}
    bottom_sigs = {x.signature for x in selected_bottom}
    result = copy.deepcopy(verse)
    new_groups: list[AlignmentGroup] = []

    # Detach selected tokens. Preserve every nonselected token. Groups that lose one side
    # remain valid because tC itself uses empty bottomWords for unaligned source tokens.
    detached_bottom: list[TokenRef] = []
    for group in result.alignments:
        keep_top = [x for x in group.top_words if x.signature not in top_sigs]
        keep_bottom = [x for x in group.bottom_words if x.signature not in bottom_sigs]
        detached_bottom.extend(x for x in group.bottom_words if x.signature in bottom_sigs)
        if keep_top or keep_bottom:
            new_groups.append(AlignmentGroup(keep_top, keep_bottom))

    # Remove selected target tokens from wordBank; selected aligned target tokens have
    # already been detached above.
    result.word_bank = [x for x in result.word_bank if x.signature not in bottom_sigs]
    new_groups.append(AlignmentGroup(list(selected_top), list(selected_bottom)))
    result.alignments = new_groups
    normalize_verse(result)
    return result


def unalign_bottom(verse: VerseAlignment, selected_bottom: list[TokenRef]) -> VerseAlignment:
    if not selected_bottom:
        raise AlignmentError('Select at least one target-language bottomWord.')
    sigs = {x.signature for x in selected_bottom}
    result = copy.deepcopy(verse)
    bank = {x.signature: x for x in result.word_bank}
    for group in result.alignments:
        removed = [x for x in group.bottom_words if x.signature in sigs]
        group.bottom_words = [x for x in group.bottom_words if x.signature not in sigs]
        for x in removed:
            bank[x.signature] = x
    result.word_bank = list(bank.values())
    normalize_verse(result)
    return result


def normalize_verse(verse: VerseAlignment) -> None:
    # Remove truly empty groups and ensure bottomWord type is retained.
    verse.alignments = [g for g in verse.alignments if g.top_words or g.bottom_words]
    verse.word_bank = [TokenRef(x.word, x.occurrence, x.occurrences, x.strong, x.lemma, x.morph, x.type or 'bottomWord') for x in verse.word_bank]
    for group in verse.alignments:
        group.bottom_words = [TokenRef(x.word, x.occurrence, x.occurrences, x.strong, x.lemma, x.morph, x.type or 'bottomWord') for x in group.bottom_words]


def validate_proposal(verse: VerseAlignment, proposal: dict[str, Any]) -> list[dict[str, Any]]:
    inv = make_inventory(verse)
    groups = proposal.get('groups')
    if not isinstance(groups, list):
        raise AlignmentError('AI proposal has no groups array.')
    seen_h: set[str] = set(); seen_t: set[str] = set()
    clean: list[dict[str, Any]] = []
    for i, g in enumerate(groups):
        if not isinstance(g, dict):
            raise AlignmentError(f'AI group {i + 1} is not an object.')
        hids = g.get('top_ids', []); tids = g.get('bottom_ids', [])
        if not isinstance(hids, list) or not isinstance(tids, list) or not hids:
            raise AlignmentError(f'AI group {i + 1} must contain top_ids and bottom_ids arrays, with at least one top id.')
        for hid in hids:
            if hid not in inv.top_ids: raise AlignmentError(f'AI returned unknown source token id: {hid}')
            if hid in seen_h: raise AlignmentError(f'AI reused source token id: {hid}')
            seen_h.add(hid)
        for tid in tids:
            if tid not in inv.bottom_ids: raise AlignmentError(f'AI returned unknown target token id: {tid}')
            if tid in seen_t: raise AlignmentError(f'AI reused target token id: {tid}')
            seen_t.add(tid)
        clean.append({
            'top_ids': hids,
            'bottom_ids': tids,
            'confidence': float(g.get('confidence', 0) or 0),
            'reason': str(g.get('reason', '') or ''),
        })
    return clean


def validate_preparation_proposal(verse: VerseAlignment, proposal: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate an automatic AI preparation proposal without allowing it to rewrite
    already-established human alignment relationships.

    Full Verse Review may fill gaps in an incomplete verse, but existing non-empty
    topWords↔bottomWords groups are human/project evidence and must remain represented
    together in the proposal. A proposal may extend such a group with additional tokens,
    but it may not detach or remap an already-aligned target token.
    """
    groups = validate_proposal(verse, proposal)
    inv = make_inventory(verse)

    proposed: list[tuple[set[str], set[str]]] = []
    for g in groups:
        proposed.append((
            {inv.top_ids[x].signature for x in g['top_ids']},
            {inv.bottom_ids[x].signature for x in g['bottom_ids']},
        ))

    for existing in verse.alignments:
        if not existing.top_words or not existing.bottom_words:
            continue
        top_sigs = {x.signature for x in existing.top_words}
        bottom_sigs = {x.signature for x in existing.bottom_words}
        if not any(top_sigs.issubset(pt) and bottom_sigs.issubset(pb) for pt, pb in proposed):
            raise AlignmentError(
                'AI preparation proposal would alter an existing project alignment. '
                'Full Verse Review may fill alignment gaps, but it may not remap already-aligned tokens.'
            )
    return groups


def apply_proposal(verse: VerseAlignment, proposal: dict[str, Any]) -> VerseAlignment:
    groups = validate_proposal(verse, proposal)
    inv = make_inventory(verse)
    result = VerseAlignment([], [])
    used_h: set[str] = set(); used_t: set[str] = set()
    for g in groups:
        result.alignments.append(AlignmentGroup(
            [inv.top_ids[x] for x in g['top_ids']],
            [inv.bottom_ids[x] for x in g['bottom_ids']],
        ))
        used_h.update(g['top_ids']); used_t.update(g['bottom_ids'])
    # Never discard model-omitted tokens: keep Hebrew as explicit unaligned groups and
    # Tamil in wordBank.
    for hid, tok in inv.top_ids.items():
        if hid not in used_h:
            result.alignments.append(AlignmentGroup([tok], []))
    result.word_bank = [tok for tid, tok in inv.bottom_ids.items() if tid not in used_t]
    normalize_verse(result)
    return result
