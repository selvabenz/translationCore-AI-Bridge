from __future__ import annotations

import re
from dataclasses import replace
from typing import Iterable

from .models import AICheckReview, QAIssue


_SEVERITY_RANK = {'critical': 0, 'high': 1, 'medium': 2, 'editorial': 3, 'info': 4}
_NEXT_LOWER = {'critical': 'high', 'high': 'medium', 'medium': 'editorial', 'editorial': 'info', 'info': 'info'}
_THRESHOLDS = {'critical': 0.90, 'high': 0.82, 'medium': 0.70, 'editorial': 0.68, 'info': 0.50}


def _norm(s: str) -> str:
    return re.sub(r'\W+', ' ', str(s or '').lower()).strip()


def gate_ai_issues(issues: Iterable[QAIssue]) -> tuple[list[QAIssue], list[QAIssue]]:
    """Conservative deterministic gate for AI QA findings.

    Goals: reduce false-positive reviewer load without hiding high-confidence evidence-backed
    findings. Low-confidence claims are suppressed; confidence below the severity threshold is
    downgraded. Near-duplicate issues are collapsed, keeping the stronger finding.
    """
    active: list[QAIssue] = []
    suppressed: list[QAIssue] = []
    seen: dict[tuple[str, str, str], QAIssue] = {}
    for original in issues:
        q = replace(original)
        conf = float(q.confidence or 0.0)
        detail_low = q.detail.lower()
        has_evidence = 'evidence:' in detail_low or bool(q.check_id) or bool(q.group_id)
        safety_retained = False
        # Low-confidence routine speculation is not priority reviewer work, but a model-labeled
        # Critical/High concern is never hidden outright: it is downgraded and kept visible.
        if q.source.lower() in ('openai', 'ai') and conf < 0.52 and q.severity not in ('critical', 'high'):
            q.detail = f'{q.detail}\n\nSuppressed by confidence gate ({conf:.0%}); available in low-confidence audit.'
            suppressed.append(q)
            continue
        if q.source.lower() in ('openai', 'ai') and conf < 0.52 and q.severity in ('critical', 'high'):
            old = q.severity
            q.severity = 'medium'  # retain as visible human-review work
            q.detail = f'{q.detail}\n\nSafety gate: low-confidence {old} claim retained as MEDIUM review ({conf:.0%}) rather than hidden.'
            safety_retained = True
        required = _THRESHOLDS.get(q.severity, 0.70)
        if (not safety_retained) and q.source.lower() in ('openai', 'ai') and (conf < required or (q.severity in ('critical', 'high') and not has_evidence)):
            old = q.severity
            q.severity = _NEXT_LOWER.get(q.severity, q.severity)  # type: ignore[assignment]
            q.detail = f'{q.detail}\n\nConfidence gate: {old} → {q.severity} ({conf:.0%}); stronger evidence is required for {old}.'
        key = (q.code, _norm(q.title), str(q.check_id or ''))
        prior = seen.get(key)
        if prior is None:
            seen[key] = q
        else:
            pc = float(prior.confidence or 0.0)
            if conf > pc or _SEVERITY_RANK.get(q.severity, 9) < _SEVERITY_RANK.get(prior.severity, 9):
                seen[key] = q
    active = list(seen.values())
    active.sort(key=lambda x: (_SEVERITY_RANK.get(x.severity, 9), -(float(x.confidence or 0.0)), x.title))
    return active, suppressed


def gate_check_reviews(reviews: Iterable[AICheckReview]) -> list[AICheckReview]:
    out: list[AICheckReview] = []
    for original in reviews:
        r = replace(original, evidence_used=list(original.evidence_used), proposed_selection_ids=list(original.proposed_selection_ids), proposed_selection_text=list(original.proposed_selection_text))
        conf = float(r.confidence or 0.0)
        evidence_count = len(r.evidence_used)
        if r.verdict in ('pass', 'problem') and conf < 0.64:
            old = r.verdict
            r.verdict = 'review'
            if r.severity in ('critical', 'high'):
                r.severity = 'medium'
            r.rationale = (r.rationale + f'\n\nConfidence gate: {old} changed to review at {conf:.0%}; human confirmation required.').strip()
        if r.severity == 'critical' and (conf < 0.90 or evidence_count == 0):
            r.severity = 'high'
            r.rationale = (r.rationale + '\n\nSeverity gate: Critical requires ≥90% confidence and explicit Knowledge Base evidence.').strip()
        elif r.severity == 'high' and conf < 0.80:
            r.severity = 'medium'
            r.rationale = (r.rationale + '\n\nSeverity gate: High-confidence evidence threshold was not met.').strip()
        out.append(r)
    return out
