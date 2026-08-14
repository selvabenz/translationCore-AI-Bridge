from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def _selection_text(entry:dict)->str:
    sel=entry.get('selections')
    if not isinstance(sel,list): return ''
    return ' '.join(str(x.get('text','')).strip() for x in sel if isinstance(x,dict) and str(x.get('text','')).strip()).strip()


def translation_words_book_analytics(project) -> dict[str, Any]:
    groups: dict[str,dict[str,Any]]={}
    for e in project._load_index_tool('translationWords'):
        c=e.get('contextId',{}) if isinstance(e,dict) else {}; gid=str(c.get('groupId',''))
        if not gid: continue
        g=groups.setdefault(gid,{'conceptId':gid,'total':0,'checked':0,'invalidated':0,'nothingToSelect':0,'renderings':Counter(),'references':[]})
        g['total']+=1
        if e.get('invalidated'): g['invalidated']+=1
        if e.get('nothingToSelect'): g['nothingToSelect']+=1
        text=_selection_text(e)
        if isinstance(e.get('selections'),list) or e.get('nothingToSelect'):
            g['checked']+=1
        if text: g['renderings'][text]+=1
        r=c.get('reference',{}) if isinstance(c,dict) else {}
        g['references'].append({'reference':f"{r.get('chapter')}:{r.get('verse')}",'sourceQuote':c.get('quoteString',''),'rendering':text,'invalidated':bool(e.get('invalidated',False))})
    rules={str(r.get('conceptId')):r for r in project.terminology_rules()}
    out=[]
    for gid,g in groups.items():
        counts=g.pop('renderings'); rule=rules.get(gid,{})
        approved=set(rule.get('approvedRenderings',[]) or []); allowed=set(rule.get('allowedAlternatives',[]) or []); rejected=set(rule.get('rejectedRenderings',[]) or [])
        rendering_rows=[]; unexplained=0
        for text,count in counts.most_common():
            status='approved' if text in approved else 'allowed' if text in allowed else 'rejected' if text in rejected else 'unclassified'
            if status in ('rejected','unclassified'): unexplained += count
            rendering_rows.append({'text':text,'count':count,'status':status})
        out.append({**g,'renderings':rendering_rows,'distinctRenderings':len(counts),'unexplainedOccurrences':unexplained,'hasHumanRule':bool(rule),'humanRule':rule})
    out.sort(key=lambda x:(-x['unexplainedOccurrences'],-x['distinctRenderings'],x['conceptId']))
    return {'bookId':project.book_id,'conceptCount':len(out),'concepts':out}


def exception_first_queue(project) -> list[dict[str,Any]]:
    rows=[]
    ai={(str(x.get('chapter')),str(x.get('verse'))):x for x in project.list_ai_review_results()}
    for ch in project.chapters():
        for vs in project.verses(ch):
            if vs=='front': continue
            saved=ai.get((str(ch),str(vs)),{}); cache=project.ai_review_cache_status(ch,vs)
            critical=high=medium=0
            for q in saved.get('qaIssues',[]) if isinstance(saved.get('qaIssues'),list) else []:
                sev=str(q.get('severity','medium')).lower()
                if sev=='critical':critical+=1
                elif sev=='high':high+=1
                elif sev=='medium':medium+=1
            for r in saved.get('checkReviews',[]) if isinstance(saved.get('checkReviews'),list) else []:
                if str(r.get('verdict','')).lower() in ('problem','review') or float(r.get('confidence',0) or 0)<.7:
                    sev=str(r.get('severity','medium')).lower()
                    if sev=='critical':critical+=1
                    elif sev=='high':high+=1
                    elif sev=='medium':medium+=1
            wa=project.word_alignment_state(ch,vs)
            checks=project.checks_for_verse(ch,vs)
            invalid=sum(1 for e in checks if bool(e.get('invalidated')) or (e.get('selections') not in (False,None) and project.check_staleness(ch,vs,str(e.get('contextId',{}).get('checkId','')))=='stale'))
            discussion=sum(1 for d in project.decisions_for_verse(ch,vs) if d.get('decision')=='needs_discussion')
            review=project.load_review_state(ch,vs) or {}; final_state=str(review.get('status',''))
            if critical or high or cache in ('stale','missing') or invalid or wa=='invalid' or discussion or final_state.startswith('stale'):
                rows.append({'chapter':str(ch),'verse':str(vs),'critical':critical,'high':high,'medium':medium,'cache':cache,'wordAlignment':wa,'invalidChecks':invalid,'discussions':discussion,'finalState':final_state,'summary':str(saved.get('summary',''))})
    rank={'stale':0,'missing':1,'current':2}
    rows.sort(key=lambda r:(-r['critical'],-r['high'],-r['invalidChecks'],-r['discussions'],rank.get(r['cache'],9),int(r['chapter']) if r['chapter'].isdigit() else 999,int(r['verse']) if r['verse'].isdigit() else 999))
    return rows
