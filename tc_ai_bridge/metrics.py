from __future__ import annotations

import json, os, tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _atomic(path:Path,data:Any):
    path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(dir=str(path.parent),prefix=path.name+'.',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

class MetricsStore:
    def __init__(self,companion_dir:Path,book_id:str):
        self.path=Path(companion_dir)/'metrics'/f'{book_id}.json'; self.book_id=book_id

    def load(self)->dict[str,Any]:
        if self.path.exists():
            try:
                d=json.loads(self.path.read_text('utf-8')); return d if isinstance(d,dict) else {}
            except Exception: pass
        return {'schemaVersion':1,'bookId':self.book_id,'counters':{},'tokens':{'input':0,'output':0,'total':0},'estimatedCostUSD':0.0,'events':[]}

    def event(self,name:str,**fields:Any)->None:
        if os.getenv('TC_AI_BRIDGE_TEST_MODE')=='1' and not fields.pop('_force_test_write',False):
            return
        d=self.load(); counters=Counter(d.get('counters',{})); counters[name]+=1; d['counters']=dict(counters)
        ev={'timestamp':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'name':name,**fields}; events=list(d.get('events',[])); events.append(ev); d['events']=events[-2000:]
        if 'input_tokens' in fields: d.setdefault('tokens',{})['input']=int(d['tokens'].get('input',0))+int(fields.get('input_tokens',0) or 0)
        if 'output_tokens' in fields: d.setdefault('tokens',{})['output']=int(d['tokens'].get('output',0))+int(fields.get('output_tokens',0) or 0)
        if 'total_tokens' in fields: d.setdefault('tokens',{})['total']=int(d['tokens'].get('total',0))+int(fields.get('total_tokens',0) or 0)
        if 'estimated_cost_usd' in fields: d['estimatedCostUSD']=float(d.get('estimatedCostUSD',0))+float(fields.get('estimated_cost_usd',0) or 0)
        _atomic(self.path,d)

    def summary(self)->dict[str,Any]:
        d=self.load(); c=d.get('counters',{})
        accepted=int(c.get('human_accept',0)); rejected=int(c.get('human_reject',0)); edited=int(c.get('human_edit',0)); discussions=int(c.get('human_discussion',0)); decisions=accepted+rejected+edited+discussions
        denominator=max(1,accepted+rejected+edited)
        events=d.get('events',[]) if isinstance(d.get('events'),list) else []
        prepared_checks=sum(int(e.get('checks',0) or 0) for e in events if e.get('name') in ('ai_prepared_verse','ai_prepared_batch'))
        prepared_issues=sum(int(e.get('issues',0) or 0) for e in events if e.get('name') in ('ai_prepared_verse','ai_prepared_batch'))
        cache_skips=sum(int(e.get('skipped',0) or 0) for e in events if e.get('name') in ('ai_prepared_batch','cache_skip'))
        confirmed=sum(1 for e in events if e.get('name')=='qa_decision' and e.get('decision')=='accepted')
        qa_decisions=sum(1 for e in events if e.get('name')=='qa_decision')
        return {**d,
            'acceptanceRate':accepted/denominator,
            'humanEditRate':edited/denominator,
            'rejectionRate':rejected/denominator,
            'humanDecisionCount':decisions,
            'aiPreparedCheckCount':prepared_checks,
            'aiPreparedFindingCount':prepared_issues,
            'unchangedReviewCacheSkips':cache_skips,
            'confirmedQAFindingRate':(confirmed/qa_decisions if qa_decisions else None),
            'measurementNote':'These are observed workflow metrics, not an inferred claim of time saved. Compare against a manual-review baseline for the same team/project.'
        }
