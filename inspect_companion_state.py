from __future__ import annotations

import argparse, json, os
from datetime import datetime
from pathlib import Path

TEST_MARKERS=('Mock full review','mock semantic match','Mock QA','Tester','test quote','Production discussion test')


def scan(root: Path):
    projects=root/'projects'
    rows=[]
    for pp in sorted(projects.iterdir() if projects.exists() else []):
        if not pp.is_dir(): continue
        c=pp/'.apps'/'translationCoreAI'
        if not c.exists(): continue
        files=[p for p in c.rglob('*') if p.is_file()]
        newest=max((p.stat().st_mtime for p in files),default=c.stat().st_mtime)
        marker_hits=[]
        for p in files:
            if p.suffix.lower() not in ('.json','.txt','.log'): continue
            try: text=p.read_text('utf-8',errors='ignore')
            except Exception: continue
            found=[m for m in TEST_MARKERS if m.lower() in text.lower()]
            if found: marker_hits.append((p,found))
        rows.append((pp.name,c,len(files),newest,marker_hits))
    return rows


def main():
    ap=argparse.ArgumentParser(description='Read-only inspection of translationCoreAI companion state.')
    ap.add_argument('root',help='translationCore data folder containing projects')
    args=ap.parse_args(); root=Path(args.root).resolve()
    if not (root/'projects').is_dir() and (root/'translationCore'/'projects').is_dir(): root=root/'translationCore'
    if not (root/'projects').is_dir(): raise SystemExit(f'No projects folder under {root}')
    print(f'Read-only scan: {root}')
    rows=scan(root)
    if not rows:
        print('No .apps\\translationCoreAI companion directories found.')
        return 0
    for name,c,count,newest,hits in rows:
        print('\nPROJECT:',name)
        print(' Companion:',c)
        print(' Files:',count)
        print(' Newest:',datetime.fromtimestamp(newest).isoformat(timespec='seconds'))
        if hits:
            print(' Possible automated-test markers:')
            for p,found in hits[:25]: print('  -',p.relative_to(c),':',', '.join(found))
        else:
            print(' No known v0.6.x automated-test text markers found.')
    print('\nNothing was changed. Do not delete companion state unless you have first backed it up and confirmed it is test-only.')
    return 0

if __name__=='__main__': raise SystemExit(main())
