from __future__ import annotations
import json, sys
from pathlib import Path

root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
if (root/'translationCore').is_dir(): root=root/'translationCore'
projects=[]; all_tn=set(); all_tw=set(); check_types=set(); index_tools=set()
for p in sorted((root/'projects').iterdir()):
    if not (p/'manifest.json').exists(): continue
    m=json.loads((p/'manifest.json').read_text('utf8'))
    bid=m['project']['id']; tc=p/'.apps/translationCore'
    item={'folder':p.name,'book_id':bid,'book_name':m['project'].get('name'),'target_language':m.get('target_language',{}).get('name'),'tc_version':m.get('tc_version'),'tc_edit_version':m.get('tc_edit_version')}
    ad=tc/'alignmentData'/bid; item['alignment_chapters']=len(list(ad.glob('*.json'))); item['alignment_verses']=0; item['alignment_groups']=0; item['word_bank_tokens']=0
    for f in ad.glob('*.json'):
        try:d=json.loads(f.read_text('utf8'))
        except:continue
        item['alignment_verses']+=len(d)
        for v in d.values(): item['alignment_groups']+=len(v.get('alignments',[])); item['word_bank_tokens']+=len(v.get('wordBank',[]))
    item['checkData']={}
    cd=tc/'checkData'
    if cd.exists():
        for d in cd.iterdir():
            if d.is_dir(): item['checkData'][d.name]=len(list(d.rglob('*.json'))); check_types.add(d.name)
    item['indexes']={}
    idx=tc/'index'
    if idx.exists():
        for d in idx.iterdir():
            if d.is_dir(): item['indexes'][d.name]=len(list(d.rglob('*.json'))); index_tools.add(d.name)
    for tool,target in [('translationNotes',all_tn),('translationWords',all_tw)]:
        b=idx/tool/bid
        if b.exists():
            for f in b.glob('*.json'):
                try:data=json.loads(f.read_text('utf8'))
                except:continue
                if isinstance(data,list):
                    for e in data:
                        gid=e.get('contextId',{}).get('groupId') if isinstance(e,dict) else None
                        if gid: target.add(gid)
    projects.append(item)
out={'source_root':str(root),'projects':projects,'checkData_types':sorted(check_types),'index_tools':sorted(index_tools),'translationNotes_groupIds':sorted(all_tn),'translationWords_groupIds':sorted(all_tw)}
print(json.dumps(out,ensure_ascii=False,indent=2))
