from __future__ import annotations
import argparse,json
from pathlib import Path
from tc_ai_bridge.tc_project import TranslationCoreRoot
from tc_ai_bridge.knowledge_base import TranslationHelpsKnowledgeBase


def main():
    ap=argparse.ArgumentParser(description='Audit translationCore AI Bridge knowledge coverage')
    ap.add_argument('root',help='translationCore root or its parent')
    ap.add_argument('--out',default='knowledge_audit.json')
    args=ap.parse_args()
    root=TranslationCoreRoot(args.root)
    report={'translationCoreRoot':str(root.path),'projects':[],'totals':{'checks':0,'missingEvidence':0}}
    for p in root.projects():
        kb=TranslationHelpsKnowledgeBase(p); item={'bookId':p.book_id,'project':p.summary.display_name,'inventory':kb.inventory(),'checks':0,'missingEvidence':[]}
        for ch in p.chapters():
            for vs in p.verses(ch):
                for e in p.checks_for_verse(ch,vs):
                    item['checks']+=1; ctx=e.get('contextId',{}); kinds={x.kind for x in kb.evidence_for_check(e)}
                    missing=False
                    if ctx.get('tool')=='translationNotes':missing=not {'translationNote','translationAcademy'} <= kinds
                    elif ctx.get('tool')=='translationWords':missing='translationWords' not in kinds
                    if missing:item['missingEvidence'].append({'chapter':ch,'verse':vs,'tool':ctx.get('tool'),'groupId':ctx.get('groupId'),'checkId':ctx.get('checkId'),'evidenceKinds':sorted(kinds)})
        report['projects'].append(item);report['totals']['checks']+=item['checks'];report['totals']['missingEvidence']+=len(item['missingEvidence'])
    Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['totals'],indent=2))

if __name__=='__main__':main()
