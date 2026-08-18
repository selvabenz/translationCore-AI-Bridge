from __future__ import annotations

"""Small Unicode helpers for caret safety in Indic-script Tk editors.

Tk's Text widget indexes Unicode code points. Complex Indic graphemes can span several code
points (base + vowel sign, virama + consonant, ZWJ/ZWNJ sequences). A mouse click may therefore
place the insertion cursor inside a shaping cluster. On Windows this can make Tamil text look as
if a glyph has been split. These helpers keep the caret on conservative grapheme boundaries.

This is deliberately narrower than the full Unicode grapheme-break algorithm: it protects the
combining-mark / joiner / virama sequences used by the target-language plugins bundled with the
Bridge, without introducing a third-party runtime dependency.
"""

import unicodedata

ZWJ = "\u200d"
ZWNJ = "\u200c"
JOINERS = {ZWJ, ZWNJ}
INDIC_VIRAMAS = {
    "\u094d",  # Devanagari
    "\u09cd",  # Bengali
    "\u0a4d",  # Gurmukhi
    "\u0acd",  # Gujarati
    "\u0bcd",  # Tamil
    "\u0c4d",  # Telugu
    "\u0ccd",  # Kannada
    "\u0d4d",  # Malayalam
}


def _is_mark(ch: str) -> bool:
    return bool(ch) and unicodedata.category(ch).startswith("M")


def indic_grapheme_boundaries(text: str) -> list[int]:
    """Return conservative insertion boundaries for Indic-script text.

    The first and last positions are always included. Combining marks stay with their base;
    virama/joiner sequences stay with the following code point.
    """
    s = str(text or "")
    if not s:
        return [0]
    boundaries = [0]
    i = 0
    n = len(s)
    while i < n:
        i += 1
        while i < n:
            ch = s[i]
            prev = s[i - 1]
            if _is_mark(ch) or ch in JOINERS or prev in JOINERS or prev in INDIC_VIRAMAS:
                i += 1
                continue
            break
        boundaries.append(i)
    return boundaries


def nearest_grapheme_boundary(text: str, offset: int) -> int:
    """Snap ``offset`` to the nearest conservative boundary (ties prefer the right boundary)."""
    s = str(text or "")
    pos = max(0, min(len(s), int(offset)))
    bounds = indic_grapheme_boundaries(s)
    if pos in bounds:
        return pos
    left = max((b for b in bounds if b < pos), default=0)
    right = min((b for b in bounds if b > pos), default=len(s))
    return right if (right - pos) <= (pos - left) else left


def previous_grapheme_boundary(text: str, offset: int) -> int:
    pos = max(0, min(len(str(text or "")), int(offset)))
    return max((b for b in indic_grapheme_boundaries(text) if b < pos), default=0)


def next_grapheme_boundary(text: str, offset: int) -> int:
    s = str(text or "")
    pos = max(0, min(len(s), int(offset)))
    return min((b for b in indic_grapheme_boundaries(s) if b > pos), default=len(s))
