from __future__ import annotations

import json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLES=('translator','reviewer','consultant','administrator')

def _atomic(p:Path,d:Any):
    p.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(dir=str(p.parent),prefix=p.name+'.',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(d,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

class TeamWorkflow:
    def __init__(self,companion:Path,book_id:str): self.root=Path(companion)/'team'; self.book_id=book_id
    @property
    def config_path(self): return self.root/'team.json'
    def config(self):
        if self.config_path.exists():
            try:return json.loads(self.config_path.read_text('utf-8'))
            except Exception:pass
        return {'schemaVersion':1,'members':[],'approvalPolicy':{'finalVerseRoles':['reviewer','consultant','administrator'],'finalChapterRoles':['consultant','administrator']}}
    def save_config(self,d): _atomic(self.config_path,d)
    def add_member(self,name:str,role:str):
        if role not in ROLES: raise ValueError('Invalid role')
        d=self.config(); members=[m for m in d.get('members',[]) if m.get('name')!=name]; members.append({'name':name,'role':role}); d['members']=members; self.save_config(d)
    def role_for(self,name:str)->str:
        for m in self.config().get('members',[]):
            if m.get('name')==name:return str(m.get('role','reviewer'))
        return 'reviewer'
    def can_final_approve(self,name:str,scope:str='verse')->bool:
        role=self.role_for(name); key='finalVerseRoles' if scope=='verse' else 'finalChapterRoles'
        return role in self.config().get('approvalPolicy',{}).get(key,[])
    def assignment_path(self,ch,vs): return self.root/'assignments'/self.book_id/str(ch)/f'{vs}.json'
    def assign(self,ch,vs,assignee:str,status:str='assigned'):
        d={'bookId':self.book_id,'chapter':str(ch),'verse':str(vs),'assignee':assignee,'status':status,'modifiedTimestamp':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}; _atomic(self.assignment_path(ch,vs),d); return d
    def assignment(self,ch,vs):
        p=self.assignment_path(ch,vs)
        if p.exists():
            try:return json.loads(p.read_text('utf-8'))
            except Exception: pass
        return None
