from __future__ import annotations

import re

# tC project chapter JSON contains inline USFM markers. These helpers are deliberately
# conservative: they never rewrite source text.
PAIRED_MARKERS = ('f', 'x', 'add', 'nd', 'wj', 'qt', 'k', 'bd', 'it', 'em')


def strip_usfm(text: str) -> str:
    # Remove footnotes/crossrefs including their contents for reader display/token ordering.
    text = re.sub(r'\\f\s.*?\\f\*', ' ', text, flags=re.S)
    text = re.sub(r'\\x\s.*?\\x\*', ' ', text, flags=re.S)
    # Remove character/paragraph markers but keep their content.
    text = re.sub(r'\\[A-Za-z0-9+_-]+\*?', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def whitespace_tokens(text: str) -> list[str]:
    cleaned = strip_usfm(text)
    if not cleaned:
        return []
    # Preserve Tamil/Hebrew combining marks by splitting only on whitespace, then trim
    # ordinary punctuation from token boundaries.
    trim_chars = ' \t\r\n.,;:!?“”‘’"\'()[]{}<>—–…।॥'
    out = []
    for raw in cleaned.split():
        token = raw.strip(trim_chars)
        if token:
            out.append(token)
    return out


def marker_balance_issues(text: str) -> list[str]:
    issues: list[str] = []
    for marker in PAIRED_MARKERS:
        opens = len(re.findall(rf'\\{re.escape(marker)}(?:\s|\+)', text))
        closes = len(re.findall(rf'\\{re.escape(marker)}\*', text))
        if opens != closes:
            issues.append(f'Unbalanced \\{marker}: {opens} open, {closes} close')
    return issues
