from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import time
from dataclasses import dataclass
from typing import Any, Callable

from .alignment_engine import apply_proposal, make_inventory, validate_proposal, validate_preparation_proposal
from .models import AICheckReview, QAIssue, VerseAlignment
from .tc_project import TranslationCoreProject
from .model_router import estimate_cost
from .cache_engine import dependency_snapshot
from .security import ai_payload_manifest
from .plugins import PluginRegistry
from .review_policy import gate_ai_issues, gate_check_reviews


class AIError(RuntimeError):
    pass


@dataclass
class AIUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_input_tokens: int = 0


Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


def default_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise AIError(f'Network error contacting OpenAI: {e.reason}') from e


class OpenAIResponsesClient:
    ENDPOINT = 'https://api.openai.com/v1/responses'
    MODELS_ENDPOINT = 'https://api.openai.com/v1/models'

    def __init__(self, api_key: str, model: str = 'gpt-5.6', transport: Transport = default_transport, timeout: float = 240.0, reasoning_effort: str = 'medium'):
        if not api_key.strip():
            raise AIError('No OpenAI API key is configured.')
        self.api_key = api_key.strip()
        self.model = model.strip() or 'gpt-5.6'
        self.transport = transport
        self.timeout = timeout
        self.reasoning_effort = reasoning_effort if reasoning_effort in ('none','low','medium','high','xhigh','max') else 'medium'
        self.last_usage = AIUsage()
        self.last_cost_usd = 0.0
        self.last_privacy_manifest: dict[str, Any] = {}

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        # Some wrappers expose output_text. Raw Responses API uses output[].content[].text.
        direct = data.get('output_text')
        if isinstance(direct, str) and direct:
            return direct
        parts: list[str] = []
        for item in data.get('output', []) if isinstance(data.get('output'), list) else []:
            if not isinstance(item, dict): continue
            for content in item.get('content', []) if isinstance(item.get('content'), list) else []:
                if isinstance(content, dict) and isinstance(content.get('text'), str):
                    parts.append(content['text'])
        return ''.join(parts)

    def _post_structured(self, instructions: str, input_text: str, schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            'model': self.model,
            'store': False,
            'instructions': instructions,
            'input': input_text,
            'reasoning': {'effort': self.reasoning_effort},
            'text': {
                'format': {
                    'type': 'json_schema',
                    'name': schema_name,
                    'strict': True,
                    'schema': schema,
                }
            },
        }
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'translationCore-AI-Bridge/0.7.0',
        }
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        status = 0
        raw = b''
        # Retry only transient transport/server failures. Schema/auth/input errors fail immediately.
        for attempt in range(3):
            status, raw = self.transport(self.ENDPOINT, headers, body, self.timeout)
            if status not in (408, 409, 429, 500, 502, 503, 504):
                break
            if attempt < 2:
                time.sleep(1.0 * (2 ** attempt))
        try:
            response = json.loads(raw.decode('utf-8'))
        except Exception as e:
            raise AIError(f'OpenAI returned a non-JSON response (HTTP {status}).') from e
        if status < 200 or status >= 300:
            err = response.get('error', {}) if isinstance(response, dict) else {}
            msg = err.get('message') if isinstance(err, dict) else None
            raise AIError(f'OpenAI API error HTTP {status}: {msg or "request failed"}')
        usage = response.get('usage', {}) if isinstance(response, dict) else {}
        input_details=usage.get('input_tokens_details', {}) if isinstance(usage,dict) else {}
        cached=int(input_details.get('cached_tokens',0) or 0) if isinstance(input_details,dict) else 0
        self.last_usage = AIUsage(
            int(usage.get('input_tokens', 0) or 0),
            int(usage.get('output_tokens', 0) or 0),
            int(usage.get('total_tokens', 0) or 0),
            cached,
        )
        self.last_cost_usd=estimate_cost(self.model,self.last_usage.input_tokens,self.last_usage.output_tokens,self.last_usage.cached_input_tokens)
        text = self._extract_text(response)
        if not text:
            raise AIError('OpenAI response contained no output text.')
        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            raise AIError('OpenAI output was not valid structured JSON.') from e
        if not isinstance(result, dict):
            raise AIError('OpenAI structured output was not an object.')
        return result

    def test_connection(self) -> dict[str, Any]:
        """Authenticate the API key and confirm the configured model is accessible without generating tokens."""
        url = f'{self.MODELS_ENDPOINT}/{urllib.parse.quote(self.model, safe="")}'
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {self.api_key}',
            'User-Agent': 'translationCore-AI-Bridge/0.7.0',
        }, method='GET')
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 30.0)) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        except urllib.error.URLError as e:
            raise AIError(f'Network error contacting OpenAI: {e.reason}') from e
        try:
            data = json.loads(raw.decode('utf-8'))
        except Exception as e:
            raise AIError(f'OpenAI returned a non-JSON response while testing API access (HTTP {status}).') from e
        if status < 200 or status >= 300:
            err = data.get('error', {}) if isinstance(data, dict) else {}
            msg = err.get('message') if isinstance(err, dict) else None
            raise AIError(f'OpenAI API connection test failed HTTP {status}: {msg or "request failed"}')
        if not isinstance(data, dict) or not data.get('id'):
            raise AIError('OpenAI API connection test returned an unexpected model response.')
        return data

    def propose_alignment(self, project: TranslationCoreProject, chapter: str, verse: str, alignment: VerseAlignment) -> dict[str, Any]:
        inv = make_inventory(alignment)
        language = PluginRegistry().detect_project(project, alignment, project.target_verse_text(chapter, verse))
        top = [
            {'id': tid, 'word': t.word, 'occurrence': t.occurrence, 'occurrences': t.occurrences, 'strong': t.strong, 'lemma': t.lemma, 'morph': t.morph}
            for tid, t in inv.top_ids.items()
        ]
        bottom = [
            {'id': tid, 'word': t.word, 'occurrence': t.occurrence, 'occurrences': t.occurrences}
            for tid, t in inv.bottom_ids.items()
        ]
        tc_checks = []
        for e in project.checks_for_verse(chapter, verse):
            c = e.get('contextId', {})
            tc_checks.append({
                'tool': c.get('tool'), 'groupId': c.get('groupId'), 'quoteString': c.get('quoteString'),
                'occurrenceNote': c.get('occurrenceNote'), 'existingSelections': e.get('selections'),
            })
        input_obj = {
            'reference': f'{project.book_id} {chapter}:{verse}',
            'tamil_verse': project.target_verse_text(chapter, verse),
            'hebrew_topWords': top,
            'tamil_bottomWords': bottom,
            'translationCore_checks': tc_checks,
            'language_context': language.to_dict(),
            'target_verse': project.target_verse_text(chapter, verse),
        }
        self.last_privacy_manifest = ai_payload_manifest(input_obj['reference'], input_obj)
        schema = {
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'groups': {
                    'type': 'array',
                    'items': {
                        'type': 'object', 'additionalProperties': False,
                        'properties': {
                            'top_ids': {'type': 'array', 'items': {'type': 'string'}},
                            'bottom_ids': {'type': 'array', 'items': {'type': 'string'}},
                            'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                            'reason': {'type': 'string'},
                        },
                        'required': ['top_ids', 'bottom_ids', 'confidence', 'reason'],
                    },
                },
                'review_notes': {'type': 'array', 'items': {'type': 'string'}},
            },
            'required': ['groups', 'review_notes'],
        }
        instructions = (
            f'You are a Bible translation word-alignment reviewer for {language.source_name} → {language.target_name}. '
            f'Connect ONLY the supplied existing {language.target_name} bottomWord IDs to the supplied existing {language.source_name} topWord IDs. '
            'Never invent, normalize, respell, merge text values, or create tokens. Respect occurrence metadata, source morphology, target morphology/case markers, idioms, implicit grammar, one-to-many and many-to-one alignments. '
            f'Every {language.source_name} source token should normally appear exactly once. Every {language.target_name} token should appear at most once. Leave bottom_ids empty only when source meaning is genuinely not represented. '
            f'{language.prompt_guidance} English/reference word order is secondary and must not control source-to-target alignment. Return only the schema.'
        )
        return self._post_structured(instructions, json.dumps(input_obj, ensure_ascii=False), 'tc_alignment_proposal', schema)

    def run_quality_review(self, project: TranslationCoreProject, chapter: str, verse: str, alignment: VerseAlignment) -> tuple[list[QAIssue], str]:
        inv = make_inventory(alignment)
        language = PluginRegistry().detect_project(project, alignment, project.target_verse_text(chapter, verse))
        tc_checks = []
        for e in project.checks_for_verse(chapter, verse):
            c = e.get('contextId', {})
            tc_checks.append({
                'checkId': c.get('checkId'), 'tool': c.get('tool'), 'groupId': c.get('groupId'),
                'source_quote': c.get('quoteString'), 'note': c.get('occurrenceNote'),
                'tamil_selection': e.get('selections'), 'nothingToSelect': e.get('nothingToSelect'), 'invalidated': e.get('invalidated'),
            })
        aligned = []
        for g in alignment.alignments:
            aligned.append({
                'hebrew': [{'word': x.word, 'lemma': x.lemma, 'morph': x.morph, 'strong': x.strong} for x in g.top_words],
                'tamil': [x.word for x in g.bottom_words],
            })
        input_obj = {
            'reference': f'{project.book_id} {chapter}:{verse}',
            'tamil_verse': project.target_verse_text(chapter, verse),
            'alignment_groups': aligned,
            'unaligned_tamil': [x.word for x in alignment.word_bank],
            'translationCore_checks': tc_checks,
            'language_context': language.to_dict(),
            'target_verse': project.target_verse_text(chapter, verse),
        }
        issue_schema = {
            'type': 'object', 'additionalProperties': False,
            'properties': {
                'severity': {'type': 'string', 'enum': ['critical', 'high', 'medium', 'editorial', 'info']},
                'category': {'type': 'string'},
                'title': {'type': 'string'},
                'detail': {'type': 'string'},
                'evidence': {'type': 'string'},
                'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'check_id': {'type': 'string'},
                'group_id': {'type': 'string'},
            },
            'required': ['severity', 'category', 'title', 'detail', 'evidence', 'confidence', 'check_id', 'group_id'],
        }
        schema = {
            'type': 'object', 'additionalProperties': False,
            'properties': {
                'summary': {'type': 'string'},
                'issues': {'type': 'array', 'items': issue_schema},
            },
            'required': ['summary', 'issues'],
        }
        instructions = (
            f'You are a senior Bible translation QA reviewer working from {language.source_name} → {language.target_name} alignment data and translationCore checks. '
            'Prioritize source meaning accuracy over style. Flag likely omissions, unsupported additions, wrong lexical meaning, negation/scope, participant/pronoun errors, number/person/tense relationships, key-term inconsistencies, figures of speech, note requirements, alignment meaning gaps, and target-language editorial problems only when evidence is strong. '
            f'{language.prompt_guidance} Do not demand literal correspondence when the target language naturally encodes source morphology in suffixes or phrases. '
            'Before reporting a problem, actively consider a plausible target-language explanation and existing project decisions. Do not duplicate the same underlying concern under multiple labels. '
            'Do not fabricate source evidence. A critical issue must plausibly change/reverse source meaning or corrupt data and should be reported only with high confidence. Return only the schema.'
        )
        result = self._post_structured(instructions, json.dumps(input_obj, ensure_ascii=False), 'tc_quality_review', schema)
        issues: list[QAIssue] = []
        for item in result.get('issues', []):
            evidence = str(item.get('evidence', '')).strip()
            detail = str(item.get('detail', '')).strip()
            if evidence:
                detail = f'{detail}\nEvidence: {evidence}'
            issues.append(QAIssue(
                code=f'AI_{str(item.get("category", "QA")).upper().replace(" ", "_")}',
                severity=item.get('severity', 'medium'),
                title=str(item.get('title', 'AI review item')),
                detail=detail,
                source='OpenAI',
                check_id=str(item.get('check_id', '')),
                group_id=str(item.get('group_id', '')),
                confidence=float(item.get('confidence', 0) or 0),
            ))
        issues, suppressed = gate_ai_issues(issues)
        summary = str(result.get('summary', ''))
        if suppressed:
            summary += f' · {len(suppressed)} low-confidence/duplicate AI finding(s) suppressed by reviewer-noise gate.'
        return issues, summary

    def run_full_review(self, project: TranslationCoreProject, chapter: str, verse: str, alignment: VerseAlignment, knowledge_base=None, progress_callback=None) -> tuple[list[AICheckReview], list[QAIssue], str, dict[str, Any]]:
        """AI performs the resource reading + target selection work, human reviews final evidence-backed results."""
        from .knowledge_base import TranslationHelpsKnowledgeBase

        kb = knowledge_base or TranslationHelpsKnowledgeBase(project)
        language = PluginRegistry().detect_project(project, alignment, project.target_verse_text(chapter, verse))
        if progress_callback: progress_callback(48, 'Building verse evidence package')
        inv = make_inventory(alignment)
        bottom_tokens = [
            {'id': tid, 'word': t.word, 'occurrence': t.occurrence, 'occurrences': t.occurrences}
            for tid, t in inv.bottom_ids.items()
        ]
        top_tokens = [
            {'id': tid, 'word': t.word, 'occurrence': t.occurrence, 'occurrences': t.occurrences,
             'strong': t.strong, 'lemma': t.lemma, 'morph': t.morph}
            for tid, t in inv.top_ids.items()
        ]
        aligned = []
        for g in alignment.alignments:
            aligned.append({
                'hebrew': [{'word': x.word, 'lemma': x.lemma, 'morph': x.morph, 'strong': x.strong,
                            'occurrence': x.occurrence, 'occurrences': x.occurrences} for x in g.top_words],
                'tamil': [{'word': x.word, 'occurrence': x.occurrence, 'occurrences': x.occurrences} for x in g.bottom_words],
            })

        pack = kb.evidence_pack_for_verse(chapter, verse, max_chars=42000)
        if progress_callback: progress_callback(58, 'Translation Helps evidence resolved')
        evidence_catalog: dict[str, dict[str, Any]] = {}
        check_inputs = []
        ev_n = 1
        for c in pack.get('checks', []):
            ev_ids = []
            for ev in c.get('evidence', []):
                eid = f'E{ev_n:03d}'; ev_n += 1
                evidence_catalog[eid] = ev
                ev_ids.append(eid)
            group = str(c.get('groupId') or '')
            history = kb.project_term_renderings(group, 120) if c.get('tool') == 'translationWords' else []
            check_inputs.append({
                'tool': c.get('tool'), 'groupId': group, 'checkId': c.get('checkId'),
                'source_quote': c.get('source_quote'), 'occurrence': c.get('occurrence'),
                'occurrenceNote': c.get('occurrenceNote'), 'existingSelections': c.get('existingSelections'),
                'nothingToSelect': c.get('nothingToSelect'), 'invalidated': c.get('invalidated'),
                'evidence_ids': ev_ids, 'approved_project_renderings': history,
            })
        global_evidence_ids=[]
        for ev in pack.get('global_checking_evidence', []):
            eid=f'E{ev_n:03d}'; ev_n += 1; evidence_catalog[eid]=ev; global_evidence_ids.append(eid)
        for rb in pack.get('reference_bibles', []):
            eid=f'E{ev_n:03d}'; ev_n += 1; evidence_catalog[eid]=rb

        input_obj = {
            'reference': f'{project.book_id} {chapter}:{verse}',
            'tamil_verse': project.target_verse_text(chapter, verse),
            'hebrew_topWords': top_tokens,
            'tamil_bottomWords': bottom_tokens,
            'current_alignment_groups': aligned,
            'translationCore_checks': check_inputs,
            'evidence_catalog': evidence_catalog,
            'resource_provenance': pack.get('resource_provenance', {}),
            'global_checking_evidence_ids': global_evidence_ids,
            'project_reviewer_decisions': sorted(project.project_decisions(), key=lambda d: str(d.get('modifiedTimestamp','')))[-100:],
            'human_approved_terminology_rules': project.terminology_rules(),
            'language_context': language.to_dict(),
            'target_verse': project.target_verse_text(chapter, verse),
            'source_topWords': top_tokens,
            'target_bottomWords': bottom_tokens,
        }
        self.last_privacy_manifest = ai_payload_manifest(input_obj['reference'], input_obj)

        check_schema = {
            'type': 'object', 'additionalProperties': False,
            'properties': {
                'tool': {'type': 'string'}, 'group_id': {'type': 'string'}, 'check_id': {'type': 'string'},
                'source_quote': {'type': 'string'},
                'selection_ids': {'type': 'array', 'items': {'type': 'string'}},
                'nothing_to_select': {'type': 'boolean'},
                'verdict': {'type': 'string', 'enum': ['pass','review','problem','not_applicable']},
                'severity': {'type': 'string', 'enum': ['critical','high','medium','editorial','info']},
                'rationale': {'type': 'string'}, 'suggested_correction': {'type': 'string'},
                'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
            },
            'required': ['tool','group_id','check_id','source_quote','selection_ids','nothing_to_select','verdict','severity','rationale','suggested_correction','confidence','evidence_ids'],
        }
        issue_schema = {
            'type': 'object', 'additionalProperties': False,
            'properties': {
                'severity': {'type': 'string', 'enum': ['critical','high','medium','editorial','info']},
                'category': {'type': 'string'}, 'title': {'type': 'string'}, 'detail': {'type': 'string'},
                'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'check_id': {'type': 'string'}, 'group_id': {'type': 'string'},
                'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
            },
            'required': ['severity','category','title','detail','confidence','check_id','group_id','evidence_ids'],
        }
        schema = {
            'type': 'object', 'additionalProperties': False,
            'properties': {
                'summary': {'type': 'string'},
                'check_reviews': {'type': 'array', 'items': check_schema},
                'qa_issues': {'type': 'array', 'items': issue_schema},
            },
            'required': ['summary','check_reviews','qa_issues'],
        }
        instructions = (
            f'You are a senior Bible translation reviewer operating translationCore checks for a {language.source_name} → {language.target_name} project. '
            'The human reviewer should not have to read every resource or manually find/select target words: do that preparation now, then present concise evidence-backed final results. '
            f'For EVERY supplied translationCore check, read its evidence_catalog items, understand the source quote and note/key-term concept, locate the exact existing {language.target_name} bottomWord IDs that represent it, and return those IDs. '
            f'Use ONLY supplied {language.target_name} selection IDs; never invent/normalize/rewrite tokens. selection_ids must be empty when and only when nothing_to_select is true or the concept is truly absent. '
            'For Translation Notes, apply the linked Translation Academy method/principle and judge whether the target translation handles the specific issue. '
            'For Translation Words, use the Translation Word article, TWL occurrence, source morphology, approved project renderings, and human_approved_terminology_rules. Human-approved terminology rules outrank AI preference; allow contextually justified variation. '
            'Then perform whole-verse QA using the supplied checking evidence: accuracy/completeness first, including omission, unsupported addition, wrong lexical meaning, negation/scope, participants/pronouns, number/person, commands/questions, semantic relations, figures, terminology, and stale/misaligned meaning. '
            f'Separately evaluate only the language-appropriate editorial categories: {", ".join(language.qa_categories)}. {language.prompt_guidance} '
            'False-positive discipline: before reporting any issue, test the strongest plausible explanation that the target rendering is valid, consult existing alignment/approved decisions/terminology, and report only one finding for one underlying problem. '
            'Critical findings require very high confidence and explicit evidence. Low-confidence possibilities should be review-level or omitted, not exaggerated. '
            'Reference only evidence IDs that exist in evidence_catalog. Reference Bibles/English are secondary aids, never authority over source data. '
            'Do not propose a correction merely because a literal rendering differs. Human/community final approval remains human. Return only the schema.'
        )
        if progress_callback: progress_callback(64, 'AI reviewing Notes, Words and whole verse')
        result = self._post_structured(instructions, json.dumps(input_obj, ensure_ascii=False), 'tc_full_review', schema)
        if progress_callback: progress_callback(88, 'Validating AI selections and evidence')

        reviews: list[AICheckReview] = []
        known_ids = set(inv.bottom_ids)
        for item in result.get('check_reviews', []):
            ids = [str(x) for x in item.get('selection_ids', [])]
            unknown = [x for x in ids if x not in known_ids]
            if unknown:
                raise AIError(f'AI check review referenced unknown target-language token ID(s): {", ".join(unknown)}')
            if len(ids) != len(set(ids)):
                raise AIError('AI check review duplicated a target-language token ID in one selection.')
            nothing = bool(item.get('nothing_to_select', False))
            if nothing and ids:
                raise AIError('AI check review returned both selection_ids and nothing_to_select=true.')
            texts = [inv.bottom_ids[x].word for x in ids]
            evs = [evidence_catalog[x] for x in item.get('evidence_ids', []) if x in evidence_catalog]
            reviews.append(AICheckReview(
                tool=str(item.get('tool','')), group_id=str(item.get('group_id','')), check_id=str(item.get('check_id','')),
                source_quote=str(item.get('source_quote','')), proposed_selection_ids=ids, proposed_selection_text=texts,
                nothing_to_select=nothing, verdict=str(item.get('verdict','review')), severity=item.get('severity','medium'),
                rationale=str(item.get('rationale','')), suggested_correction=str(item.get('suggested_correction','')),
                confidence=float(item.get('confidence',0) or 0), evidence_used=evs,
            ))
        # Ensure AI did not silently omit or fabricate a supplied check. Missing model rows
        # become explicit review items rather than causing the entire verse/batch to disappear.
        expected_map = {str(c.get('checkId')): c for c in check_inputs if c.get('checkId')}
        returned_ids = [x.check_id for x in reviews if x.check_id]
        extras = sorted(set(returned_ids) - set(expected_map))
        if extras:
            raise AIError(f'AI full review returned unknown translationCore check(s): {", ".join(extras[:8])}')
        if len(returned_ids) != len(set(returned_ids)):
            raise AIError('AI full review duplicated a translationCore check result.')
        missing = sorted(set(expected_map) - set(returned_ids))
        for check_id in missing:
            c = expected_map[check_id]
            evs = [evidence_catalog[x] for x in c.get('evidence_ids', []) if x in evidence_catalog]
            reviews.append(AICheckReview(
                tool=str(c.get('tool','')), group_id=str(c.get('groupId','')), check_id=check_id,
                source_quote=str(c.get('source_quote') or ''), proposed_selection_ids=[], proposed_selection_text=[],
                nothing_to_select=False, verdict='review', severity='high',
                rationale='AI response omitted this translationCore check. No automatic conclusion was accepted; rerun this verse/check or review it manually.',
                suggested_correction='', confidence=0.0, evidence_used=evs,
            ))

        issues: list[QAIssue] = []
        for item in result.get('qa_issues', []):
            evs=[evidence_catalog[x] for x in item.get('evidence_ids', []) if x in evidence_catalog]
            evidence_text='\n'.join(f"• {e.get('title','Evidence')}: {str(e.get('content',''))[:900]}" for e in evs)
            detail=str(item.get('detail','')).strip()
            if evidence_text:
                detail += '\nEvidence used:\n' + evidence_text
            issues.append(QAIssue(
                code=f'AI_{str(item.get("category","QA")).upper().replace(" ","_")}',
                severity=item.get('severity','medium'), title=str(item.get('title','AI review item')), detail=detail,
                source='OpenAI+KnowledgeBase', check_id=str(item.get('check_id','')), group_id=str(item.get('group_id','')),
                confidence=float(item.get('confidence',0) or 0),
            ))

        reviews = gate_check_reviews(reviews)
        active_issues, suppressed_issues = gate_ai_issues(issues)
        issues = active_issues
        summary = str(result.get('summary',''))
        if suppressed_issues:
            summary += f' · {len(suppressed_issues)} low-confidence/duplicate AI finding(s) suppressed.'
        saved = project.record_ai_review_result(chapter, verse, {
            'summary': summary,
            'model': self.model,
            'reasoningEffort': self.reasoning_effort,
            'estimatedCostUSD': self.last_cost_usd,
            'dependencySnapshot': dependency_snapshot(project, chapter, verse, knowledge_base, self.model),
            'resourceProvenance': pack.get('resource_provenance', {}),
            'privacyManifest': self.last_privacy_manifest,
            'checkReviews': [x.to_dict() for x in reviews],
            'qaIssues': [x.to_dict() for x in issues],
            'suppressedQaIssues': [x.to_dict() for x in suppressed_issues],
            'languageContext': language.to_dict(),
        })
        return reviews, issues, summary, {'resource_provenance': pack.get('resource_provenance', {}), 'saved_to': str(saved), 'evidence_catalog': evidence_catalog, 'model': self.model, 'reasoning_effort': self.reasoning_effort, 'estimated_cost_usd': self.last_cost_usd, 'privacy_manifest': self.last_privacy_manifest, 'language_context': language.to_dict(), 'suppressed_qa_count': len(suppressed_issues)}

    def prepare_verse_review(self, project: TranslationCoreProject, chapter: str, verse: str, alignment: VerseAlignment, knowledge_base=None, progress_callback=None) -> tuple[dict[str, Any] | None, VerseAlignment, list[AICheckReview], list[QAIssue], str, dict[str, Any]]:
        """
        One-click preparation for the human final reviewer.

        If alignment is incomplete, AI first proposes/validates a complete token alignment in memory.
        It then performs the evidence-backed tC check review and whole-verse QA against that proposed
        alignment. Nothing is written to translationCore alignmentData or checkData.
        """
        if progress_callback: progress_callback(5, 'Preparing verse review')
        needs_alignment = bool(alignment.word_bank) or any(g.top_words and not g.bottom_words for g in alignment.alignments)
        proposal: dict[str, Any] | None = None
        review_alignment = alignment
        first_usage = 0
        first_cost = 0.0
        if needs_alignment:
            if progress_callback: progress_callback(12, 'AI preparing incomplete alignment')
            proposal = self.propose_alignment(project, chapter, verse, alignment)
            # Automatic final-review preparation may fill gaps, but it must never
            # rewrite already-established project alignment relationships.
            validate_preparation_proposal(alignment, proposal)
            review_alignment = apply_proposal(alignment, proposal)
            first_usage = self.last_usage.total_tokens
            first_cost = self.last_cost_usd
            if progress_callback: progress_callback(38, 'Alignment proposal validated locally')
        else:
            if progress_callback: progress_callback(38, 'Existing alignment ready')
        reviews, issues, summary, meta = self.run_full_review(project, chapter, verse, review_alignment, knowledge_base, progress_callback=progress_callback)
        second_usage = self.last_usage.total_tokens
        second_cost = self.last_cost_usd
        total_cost = first_cost + second_cost
        meta = dict(meta)
        meta['alignment_was_ai_proposed'] = proposal is not None
        meta['total_tokens_for_prepare'] = first_usage + second_usage
        meta['estimated_cost_usd'] = total_cost
        meta['model'] = self.model
        meta['reasoning_effort'] = self.reasoning_effort
        meta['privacy_manifest'] = self.last_privacy_manifest
        saved = project.record_ai_review_result(chapter, verse, {
            'summary': summary,
            'model': self.model,
            'reasoningEffort': self.reasoning_effort,
            'estimatedCostUSD': total_cost,
            'dependencySnapshot': dependency_snapshot(project, chapter, verse, knowledge_base, self.model),
            'resourceProvenance': meta.get('resource_provenance', {}),
            'privacyManifest': self.last_privacy_manifest,
            'alignmentProposal': proposal,
            'alignmentWasAIProposed': proposal is not None,
            'reviewedAlignment': review_alignment.to_dict(),
            'checkReviews': [x.to_dict() for x in reviews],
            'qaIssues': [x.to_dict() for x in issues],
        })
        meta['saved_to'] = str(saved)
        self.last_cost_usd = total_cost
        if progress_callback: progress_callback(100, 'Verse AI review complete')
        return proposal, review_alignment, reviews, issues, summary, meta

