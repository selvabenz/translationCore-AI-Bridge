from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal['critical', 'high', 'medium', 'editorial', 'info']


@dataclass(frozen=True)
class TokenRef:
    word: str
    occurrence: int = 1
    occurrences: int = 1
    strong: str = ''
    lemma: str = ''
    morph: str = ''
    type: str = ''

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'TokenRef':
        return cls(
            word=str(data.get('word', '')),
            occurrence=int(data.get('occurrence', 1) or 1),
            occurrences=int(data.get('occurrences', 1) or 1),
            strong=str(data.get('strong', '') or ''),
            lemma=str(data.get('lemma', '') or ''),
            morph=str(data.get('morph', '') or ''),
            type=str(data.get('type', '') or ''),
        )

    def to_dict(self, bottom: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            'word': self.word,
            'occurrence': self.occurrence,
            'occurrences': self.occurrences,
        }
        if bottom or self.type:
            out['type'] = self.type or 'bottomWord'
        if self.strong:
            out['strong'] = self.strong
        if self.lemma:
            out['lemma'] = self.lemma
        if self.morph:
            out['morph'] = self.morph
        # translationCore top word key order is not semantically important.
        if not bottom:
            ordered = {}
            for key in ('word', 'strong', 'lemma', 'morph', 'occurrence', 'occurrences'):
                if key in out:
                    ordered[key] = out[key]
            return ordered
        return out

    @property
    def signature(self) -> str:
        return f'{self.word}\u241f{self.occurrence}\u241f{self.occurrences}'


@dataclass
class AlignmentGroup:
    top_words: list[TokenRef] = field(default_factory=list)
    bottom_words: list[TokenRef] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'AlignmentGroup':
        return cls(
            [TokenRef.from_dict(x) for x in data.get('topWords', [])],
            [TokenRef.from_dict(x) for x in data.get('bottomWords', [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'topWords': [x.to_dict(bottom=False) for x in self.top_words],
            'bottomWords': [x.to_dict(bottom=True) for x in self.bottom_words],
        }


@dataclass
class VerseAlignment:
    alignments: list[AlignmentGroup] = field(default_factory=list)
    word_bank: list[TokenRef] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'VerseAlignment':
        return cls(
            [AlignmentGroup.from_dict(x) for x in data.get('alignments', [])],
            [TokenRef.from_dict(x) for x in data.get('wordBank', [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'alignments': [x.to_dict() for x in self.alignments],
            'wordBank': [x.to_dict(bottom=True) for x in self.word_bank],
        }

    def all_top(self) -> list[TokenRef]:
        return [w for g in self.alignments for w in g.top_words]

    def aligned_bottom(self) -> list[TokenRef]:
        return [w for g in self.alignments for w in g.bottom_words]

    def all_bottom(self) -> list[TokenRef]:
        return self.aligned_bottom() + list(self.word_bank)


@dataclass
class QAIssue:
    code: str
    severity: Severity
    title: str
    detail: str
    source: str = 'local'
    check_id: str = ''
    group_id: str = ''
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            'code': self.code,
            'severity': self.severity,
            'title': self.title,
            'detail': self.detail,
            'source': self.source,
        }
        if self.check_id:
            data['check_id'] = self.check_id
        if self.group_id:
            data['group_id'] = self.group_id
        if self.confidence is not None:
            data['confidence'] = self.confidence
        return data


@dataclass
class AICheckReview:
    tool: str
    group_id: str
    check_id: str
    source_quote: str
    proposed_selection_ids: list[str] = field(default_factory=list)
    proposed_selection_text: list[str] = field(default_factory=list)
    nothing_to_select: bool = False
    verdict: str = 'review'  # pass | review | problem | not_applicable
    severity: Severity = 'medium'
    rationale: str = ''
    suggested_correction: str = ''
    confidence: float = 0.0
    evidence_used: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'tool': self.tool,
            'group_id': self.group_id,
            'check_id': self.check_id,
            'source_quote': self.source_quote,
            'proposed_selection_ids': list(self.proposed_selection_ids),
            'proposed_selection_text': list(self.proposed_selection_text),
            'nothing_to_select': self.nothing_to_select,
            'verdict': self.verdict,
            'severity': self.severity,
            'rationale': self.rationale,
            'suggested_correction': self.suggested_correction,
            'confidence': self.confidence,
            'evidence_used': list(self.evidence_used),
        }
