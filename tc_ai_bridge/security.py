from __future__ import annotations

import json, re
from pathlib import Path
from typing import Any

SECRET_PATTERNS=[re.compile(r'\bsk-[A-Za-z0-9_-]{12,}\b'),re.compile(r'Authorization\s*:\s*Bearer\s+\S+',re.I)]

def redact_text(text:str)->str:
    out=str(text)
    for p in SECRET_PATTERNS: out=p.sub('[REDACTED]',out)
    return out

def sanitize_for_log(value:Any)->str:
    try:text=json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value
    except Exception:text=str(value)
    return redact_text(text)

def scan_tree_for_secrets(root:Path)->list[str]:
    findings=[]
    for p in Path(root).rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix.lower() in ('.png','.jpg','.jpeg','.ico','.zip','.exe','.dll','.pyc','.pyo'): continue
        try:text=p.read_text('utf-8',errors='ignore')
        except Exception:continue
        if any(rx.search(text) for rx in SECRET_PATTERNS): findings.append(str(p))
    return findings

def ai_payload_manifest(reference:str,fields:dict[str,Any])->dict[str,Any]:
    """Human-readable privacy manifest; actual content stays local unless listed."""
    return {'reference':reference,'sentFields':sorted(fields.keys()),'containsScripture':bool(fields.get('tamil_verse')),'containsOriginalLanguage':bool(fields.get('hebrew_topWords') or fields.get('hebrew')),'containsTranslationHelps':bool(fields.get('translationCore_checks') or fields.get('evidence_catalog')),'unrelatedProjectFilesSent':False}
