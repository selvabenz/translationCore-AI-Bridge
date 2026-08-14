from __future__ import annotations

import hashlib, json
from typing import Any

PROMPT_SCHEMA_VERSION='v0.6-production-1'

def _hash(data:Any)->str:
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

def dependency_snapshot(project,chapter,verse,kb=None,model_policy:str='balanced')->dict[str,Any]:
    alignment=project.load_alignment_chapter(chapter).get(str(verse),{})
    checks=[]
    for e in project.checks_for_verse(chapter,verse):
        checks.append({k:e.get(k) for k in ('selections','nothingToSelect','invalidated','verseEdits','comments')} | {'contextId':e.get('contextId',{})})
    resources={}
    if kb is not None:
        try: resources=kb.provenance_manifest()
        except Exception:
            try: resources=kb.inventory().get('resources',{})
            except Exception: resources={}
    terminology=project.terminology_rules()
    components={
        'scripture':_hash(project.target_verse_text(chapter,verse)),
        'alignment':_hash(alignment),
        'checks':_hash(checks),
        'resources':_hash(resources),
        'terminology':_hash(terminology),
        'projectManifest':_hash({k:v for k,v in project.manifest.items() if k.startswith('tc_') or k in ('project','target_language','source_translations')}),
        'promptSchema':PROMPT_SCHEMA_VERSION,
        'modelPolicy':model_policy,
    }
    components['full']=_hash(components)
    return components

def stale_reasons(previous:dict[str,Any]|None,current:dict[str,Any])->list[str]:
    if not previous: return ['no previous dependency snapshot']
    labels={'scripture':'Scripture text changed','alignment':'Alignment changed','checks':'translationCore check state changed','resources':'Knowledge Base/resource version changed','terminology':'Human terminology rules changed','projectManifest':'Project/resource manifest changed','promptSchema':'AI prompt/schema version changed','modelPolicy':'AI model-routing policy changed'}
    return [labels.get(k,k+' changed') for k in labels if previous.get(k)!=current.get(k)]
