from __future__ import annotations

from collections import Counter
from pathlib import Path

from .models import QAIssue, VerseAlignment
from .tc_project import TranslationCoreProject
from .plugins import PluginRegistry, ProjectLanguageContext
from .usfm import marker_balance_issues, strip_usfm, whitespace_tokens


def alignment_integrity_checks(verse: VerseAlignment, target_text: str = '', target_name: str = 'Tamil', source_name: str = 'Hebrew') -> list[QAIssue]:
    issues: list[QAIssue] = []
    top = verse.all_top(); aligned_bottom = verse.aligned_bottom(); bank = verse.word_bank
    top_counts = Counter(x.signature for x in top)
    bottom_counts = Counter(x.signature for x in aligned_bottom)
    bank_counts = Counter(x.signature for x in bank)
    for sig, n in top_counts.items():
        if n > 1:
            issues.append(QAIssue('ALIGN_DUP_TOP', 'critical', f'{source_name} token aligned more than once', f'The same topWord identity appears in {n} alignment groups.'))
    for sig, n in bottom_counts.items():
        if n > 1:
            issues.append(QAIssue('ALIGN_DUP_BOTTOM', 'critical', f'{target_name} token aligned more than once', f'The same bottomWord identity appears in {n} alignment groups.'))
    overlap = set(bottom_counts) & set(bank_counts)
    if overlap:
        issues.append(QAIssue('ALIGN_BANK_OVERLAP', 'critical', f'{target_name} token both aligned and in wordBank', f'{len(overlap)} {target_name} token(s) are represented in both places.'))
    empty_bottom = sum(1 for g in verse.alignments if g.top_words and not g.bottom_words)
    if empty_bottom:
        issues.append(QAIssue('ALIGN_UNALIGNED_TOP', 'high', f'Unaligned {source_name} source tokens', f'{empty_bottom} alignment group(s) have topWords but no bottomWords.'))
    if bank:
        issues.append(QAIssue('ALIGN_UNALIGNED_BOTTOM', 'medium', f'Unaligned {target_name} target tokens', f'{len(bank)} {target_name} bottomWord token(s) remain in wordBank.'))
    for token in top + aligned_bottom + bank:
        if token.occurrence < 1 or token.occurrences < 1 or token.occurrence > token.occurrences:
            issues.append(QAIssue('ALIGN_OCCURRENCE', 'critical', 'Invalid occurrence metadata', f'{token.word}: occurrence {token.occurrence}, occurrences {token.occurrences}'))
    if target_text:
        plain = strip_usfm(target_text)
        missing = [t.word for t in aligned_bottom + bank if t.word and t.word not in plain]
        if missing:
            sample = ', '.join(missing[:8])
            issues.append(QAIssue('ALIGN_TARGET_MISMATCH', 'high', f'Alignment token not found in current {target_name} verse', f'{len(missing)} token(s) do not occur verbatim in the current verse text. Examples: {sample}. This may indicate stale alignmentData after a verse edit.'))
    return issues


def target_editorial_checks(text: str, language: ProjectLanguageContext | None = None) -> list[QAIssue]:
    issues: list[QAIssue] = []
    lang = language.target_name if language else 'Tamil'
    prefix = 'TA' if (language is None or language.target_id == 'ta') else 'LANG'
    plain = strip_usfm(text)
    if '  ' in plain:
        issues.append(QAIssue(f'{prefix}_DOUBLE_SPACE', 'editorial', 'Repeated spaces', f'The {lang} verse contains repeated spaces.'))
    tokens = whitespace_tokens(text)
    for a, b in zip(tokens, tokens[1:]):
        if a == b:
            issues.append(QAIssue(f'{prefix}_REPEAT_WORD', 'medium', 'Consecutive repeated word', f'“{a}” occurs twice consecutively. Verify that the repetition is intentional.'))
            break
    if '\u200b' in text or '\ufeff' in text:
        issues.append(QAIssue(f'{prefix}_HIDDEN_CHAR', 'editorial', 'Hidden Unicode character', 'The verse contains a zero-width/BOM character that can cause publishing or tokenization problems.'))
    return issues


def translationcore_check_issues(project: TranslationCoreProject, chapter: str, verse: str) -> list[QAIssue]:
    issues: list[QAIssue] = []
    checks = project.checks_for_verse(chapter, verse)
    for entry in checks:
        ctx = entry.get('contextId', {})
        tool = str(ctx.get('tool', 'translationCore'))
        group = str(ctx.get('groupId', ''))
        check_id = str(ctx.get('checkId', ''))
        selection = entry.get('selections', False)
        nothing = bool(entry.get('nothingToSelect', False))
        invalid = bool(entry.get('invalidated', False))
        stale = project.check_staleness(chapter, verse, check_id) == 'stale'
        if invalid or stale:
            reason = 'invalidated' if invalid else 'stale after a later Scripture edit'
            issues.append(QAIssue('TC_INVALIDATED' if invalid else 'TC_STALE_AFTER_EDIT', 'high', f'{tool}: recheck required', f'{group} / {check_id} is {reason}.', 'translationCore', check_id, group))
        elif selection is False and not nothing:
            sev = 'medium' if tool == 'translationNotes' else 'high'
            note = str(ctx.get('occurrenceNote', '') or '')
            issues.append(QAIssue('TC_PENDING', sev, f'{tool}: unchecked item', note or f'{group} / {check_id} has no selection yet.', 'translationCore', check_id, group))
    wa_state = project.word_alignment_state(chapter, verse)
    if wa_state == 'invalid':
        issues.append(QAIssue('WA_INVALID', 'high', 'Word Alignment recheck required', 'translationCore marks Word Alignment invalid after a target-text edit.', 'translationCore'))
    states = project.check_state_for_verse(chapter, verse)
    if states.get('comments'):
        issues.append(QAIssue('TC_COMMENTS', 'info', 'Reviewer comments present', f'{len(states["comments"])} translationCore comment(s) exist for this verse.', 'translationCore'))
    if states.get('verseEdits'):
        issues.append(QAIssue('TC_VERSE_EDITS', 'info', 'Verse edit history present', f'{len(states["verseEdits"])} translationCore verse edit record(s) exist.', 'translationCore'))
    return issues


def usfm_checks(project: TranslationCoreProject, chapter: str, verse: str) -> list[QAIssue]:
    text = project.target_verse_text(chapter, verse)
    return [QAIssue('USFM_BALANCE', 'high', 'USFM marker imbalance', msg, 'local') for msg in marker_balance_issues(text)]


def run_local_qa(project: TranslationCoreProject, chapter: str, verse: str, alignment: VerseAlignment) -> list[QAIssue]:
    text = project.target_verse_text(chapter, verse)
    language = PluginRegistry().detect_project(project, alignment, text)
    issues = []
    issues += alignment_integrity_checks(alignment, text, language.target_name, language.source_name)
    issues += translationcore_check_issues(project, chapter, verse)
    issues += target_editorial_checks(text, language)
    issues += usfm_checks(project, chapter, verse)
    order = {'critical': 0, 'high': 1, 'medium': 2, 'editorial': 3, 'info': 4}
    return sorted(issues, key=lambda x: (order.get(x.severity, 9), x.title))
