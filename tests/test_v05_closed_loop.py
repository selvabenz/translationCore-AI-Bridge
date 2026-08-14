from __future__ import annotations

import copy, hashlib, json, os, shutil, tempfile, unittest
from unittest.mock import patch
from pathlib import Path

from tc_ai_bridge.alignment_engine import make_inventory
from tc_ai_bridge.tc_project import TranslationCoreProject, TranslationCoreRoot
from tc_ai_bridge.ai_client import OpenAIResponsesClient
from tc_ai_bridge.knowledge_base import TranslationHelpsKnowledgeBase
from tc_ai_bridge.models import AlignmentGroup, VerseAlignment, TokenRef, AICheckReview
from tc_ai_bridge.session import EditSession
from tc_ai_bridge.ui import BridgeApp
from tests.fixture_utils import make_lightweight_root

ROOT = Path(os.getenv('TC_TEST_ROOT', '__missing_real_backend_fixture__'))

def sha256(p: Path) -> str:
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()

@unittest.skipUnless(ROOT.exists(), 'real backend unavailable')
class ClosedLoopCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projects={p.book_id:p for p in TranslationCoreRoot(ROOT).projects()}

    def temp_project(self, book='rut'):
        td=tempfile.TemporaryDirectory(); src=self.projects[book].path; dst=Path(td.name)/src.name
        shutil.copytree(src,dst,ignore=shutil.ignore_patterns('.git','.apps/translationCoreAI'))
        return td, TranslationCoreProject(dst)

    def test_tn_tw_approval_sync_uses_real_tc_state_shape_and_index(self):
        td,p=self.temp_project('rut')
        try:
            chosen=None
            for ch in p.chapters():
                for vs in p.verses(ch):
                    if vs=='front': continue
                    inv=make_inventory(p.load_verse_alignment(ch,vs))
                    if not inv.bottom: continue
                    for e in p.checks_for_verse(ch,vs):
                        if e.get('selections') is False and not e.get('nothingToSelect'):
                            chosen=(ch,vs,e,inv); break
                    if chosen: break
                if chosen: break
            self.assertIsNotNone(chosen)
            ch,vs,e,inv=chosen; c=e['contextId']; tok=next(iter(inv.bottom_ids.values()))
            out=p.sync_check_approval(ch,vs,c['tool'],c['groupId'],c['checkId'],[{'text':tok.word,'occurrence':tok.occurrence,'occurrences':tok.occurrences}],False,'Tester')
            self.assertTrue(Path(out['selection']).exists()); self.assertTrue(Path(out['invalidated']).exists())
            sel=json.loads(Path(out['selection']).read_text(encoding='utf-8'))
            invrec=json.loads(Path(out['invalidated']).read_text(encoding='utf-8'))
            self.assertEqual(sel['contextId']['checkId'],c['checkId']); self.assertEqual(sel['username'],'Tester')
            self.assertFalse(invrec['invalidated'])
            p2=TranslationCoreProject(p.path)
            match=[x for x in p2.checks_for_verse(ch,vs) if x['contextId']['checkId']==c['checkId']][0]
            self.assertIsInstance(match['selections'],list); self.assertEqual(match['selections'][0]['text'],tok.word)
            self.assertEqual(p2.check_staleness(ch,vs,c['checkId']),'current')
        finally: td.cleanup()

    def test_word_alignment_completion_sync_removes_invalid_marker(self):
        td,p=self.temp_project('rut')
        try:
            # use a real invalid WA verse if available
            invalid_root=p.tc_dir/'tools'/'wordAlignment'/'invalid'; files=list(invalid_root.rglob('*.json'))
            self.assertTrue(files); rel=files[0].relative_to(invalid_root); ch=rel.parent.name; vs=rel.stem
            self.assertEqual(p.word_alignment_state(ch,vs),'invalid')
            completed=p.mark_word_alignment_completed(ch,vs,'Tester')
            self.assertTrue(completed.exists()); self.assertEqual(p.word_alignment_state(ch,vs),'completed')
            d=json.loads(completed.read_text(encoding='utf-8')); self.assertEqual(d['username'],'Tester'); self.assertIn('modifiedTimestamp',d)
            self.assertFalse((invalid_root/rel).exists())
        finally: td.cleanup()

    def test_human_scripture_edit_reconciles_alignment_and_propagates_stale_state(self):
        td,p=self.temp_project('rut')
        try:
            ch,vs='1','1'; before=p.target_verse_text(ch,vs); usfm=p.usfm_path(); usfm_hash=sha256(usfm) if usfm else None
            p.record_ai_review_result(ch,vs,{'summary':'before edit','checkReviews':[],'qaIssues':[]})
            p.record_review_state(ch,vs,'approved','pre-edit approval')
            new=before+' சோதனை'
            result=p.apply_scripture_edit(ch,vs,new,'Tester',['meaning'])
            self.assertEqual(p.target_verse_text(ch,vs),new)
            if usfm: self.assertEqual(sha256(usfm),usfm_hash, 'import USFM must remain unchanged like tC live edits')
            a=p.load_verse_alignment(ch,vs); self.assertTrue(any(t.word=='சோதனை' for t in a.word_bank))
            self.assertEqual(p.word_alignment_state(ch,vs),'invalid')
            self.assertEqual(p.ai_review_cache_status(ch,vs),'stale')
            self.assertEqual(p.load_review_state(ch,vs)['status'],'stale_after_verse_edit')
            self.assertTrue(Path(result['verseEdit']).exists())
            checks=p.checks_for_verse(ch,vs)
            self.assertTrue(checks)
            self.assertTrue(all(bool(e.get('verseEdits')) for e in checks))
            # A later recheck of one item becomes current even though verse-edit history remains.
            e=checks[0]; c=e['contextId']; inv=make_inventory(a); tok=next(iter(inv.bottom_ids.values()))
            p.sync_check_approval(ch,vs,c['tool'],c['groupId'],c['checkId'],[{'text':tok.word,'occurrence':tok.occurrence,'occurrences':tok.occurrences}],False,'Tester')
            self.assertEqual(p.check_staleness(ch,vs,c['checkId']),'current')
        finally: td.cleanup()

    def test_scripture_edit_can_be_reversed_as_a_new_audited_edit(self):
        td,p=self.temp_project('oba')
        try:
            ch,vs='1','1'; before=p.target_verse_text(ch,vs); changed=before+' சோதனை'
            p.apply_scripture_edit(ch,vs,changed,'Tester',['word_choice'])
            p.apply_scripture_edit(ch,vs,before,'Tester',['undo'])
            self.assertEqual(p.target_verse_text(ch,vs),before)
            edits=p.check_state_for_verse(ch,vs)['verseEdits']; self.assertGreaterEqual(len(edits),2)
            self.assertEqual(p.word_alignment_state(ch,vs),'invalid')
        finally: td.cleanup()

    def test_qa_decisions_are_current_plus_append_only_audit(self):
        td,p=self.temp_project('oba')
        try:
            key='OpenAI:OMISSION:abc123'; issue={'code':'OMISSION','severity':'critical','title':'Possible omission'}
            p.record_qa_decision('1','1',key,'accepted','confirmed',issue)
            p.record_qa_decision('1','1',key,'rejected','false positive',issue)
            d=p.qa_decisions_for_verse('1','1')[key]
            self.assertEqual(d['decision'],'rejected')
            audits=list((p.companion_dir()/'audit'/p.book_id/'1'/'1').glob('*_qa_*.json'))
            self.assertGreaterEqual(len(audits),2)
        finally: td.cleanup()

    def test_tn_sync_rebase_keeps_existing_ai_review_current(self):
        td,p=self.temp_project('rut')
        try:
            chosen=None
            for ch in p.chapters():
                for vs in p.verses(ch):
                    if vs=='front': continue
                    inv=make_inventory(p.load_verse_alignment(ch,vs))
                    if not inv.bottom: continue
                    for e in p.checks_for_verse(ch,vs):
                        if e.get('selections') is False:
                            chosen=(ch,vs,e,inv); break
                    if chosen: break
                if chosen: break
            ch,vs,e,inv=chosen; p.record_ai_review_result(ch,vs,{'summary':'reviewed','checkReviews':[],'qaIssues':[]})
            c=e['contextId']; tok=next(iter(inv.bottom_ids.values()))
            p.sync_check_approval(ch,vs,c['tool'],c['groupId'],c['checkId'],[{'text':tok.word,'occurrence':tok.occurrence,'occurrences':tok.occurrences}],False,'Tester')
            self.assertEqual(p.ai_review_cache_status(ch,vs),'stale')
            p.rebase_ai_review_fingerprint(ch,vs)
            self.assertEqual(p.ai_review_cache_status(ch,vs),'current')
        finally: td.cleanup()

    def test_human_approved_terminology_rule_is_trusted_project_knowledge(self):
        td,p=self.temp_project('rut')
        try:
            out=p.record_terminology_rule('redeem',['மீட்பவர்'],['மீட்கிறவர்'],['வாங்குபவர்'],source_lemma='גאל',strong='H1350',note='Use covenant-family redemption sense here.',username='Tester')
            self.assertTrue(out.exists())
            rules=p.terminology_rules(); self.assertEqual(len(rules),1); r=rules[0]
            self.assertEqual(r['status'],'human_approved'); self.assertEqual(r['approvedRenderings'],['மீட்பவர்']); self.assertIn('மீட்கிறவர்',r['allowedAlternatives']); self.assertEqual(r['username'],'Tester')
            # Updating the same concept replaces current rule but preserves append-only terminology audit.
            p.record_terminology_rule('redeem',['மீட்பவர்','மீட்கிறவர்'],[],['வாங்குபவர்'],source_lemma='גאל',username='Tester')
            self.assertEqual(len(p.terminology_rules()),1); self.assertEqual(len(p.terminology_rules()[0]['approvedRenderings']),2)
            audits=list((p.companion_dir()/'audit'/p.book_id/'terminology').glob('*.json')); self.assertGreaterEqual(len(audits),2)
        finally: td.cleanup()

    def test_ai_full_review_receives_human_approved_terminology_rules(self):
        src=self.projects['rut'].path
        td,tc=make_lightweight_root(ROOT,[src])
        try:
            dst=tc/'projects'/src.name
            p=TranslationCoreProject(dst); p.record_terminology_rule('redeem',['மீட்பவர்'],source_lemma='גאל',username='Tester')
            kb=TranslationHelpsKnowledgeBase(p); a=p.load_verse_alignment('1','1'); captured={}
            def transport(url,headers,body,timeout):
                req=json.loads(body.decode('utf-8')); input_obj=json.loads(req['input']); captured.update(input_obj)
                reviews=[]
                for c in input_obj.get('translationCore_checks',[]):
                    reviews.append({'tool':c['tool'],'group_id':c['groupId'],'check_id':c['checkId'],'source_quote':str(c.get('source_quote') or ''),'selection_ids':[],'nothing_to_select':True,'verdict':'review','severity':'medium','rationale':'mock','suggested_correction':'','confidence':0.5,'evidence_ids':[]})
                result={'summary':'mock','check_reviews':reviews,'qa_issues':[]}
                return 200,json.dumps({'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}).encode()
            client=OpenAIResponsesClient('fake','gpt-test',transport=transport)
            client.run_full_review(p,'1','1',a,kb)
            rules=captured.get('human_approved_terminology_rules',[])
            self.assertTrue(rules); self.assertEqual(rules[0]['conceptId'],'redeem'); self.assertEqual(rules[0]['approvedRenderings'],['மீட்பவர்'])
        finally:
            td.cleanup()

    def test_ai_review_selection_ids_resolve_by_token_signature_not_reordered_id(self):
        # AI reviewed an alignment ordered A,B. Human current alignment is ordered B,A.
        a=TokenRef('அ',1,1,type='bottomWord'); b=TokenRef('ஆ',1,1,type='bottomWord')
        h1=TokenRef('א',1,1); h2=TokenRef('ב',1,1)
        reviewed=VerseAlignment([AlignmentGroup([h1],[a]),AlignmentGroup([h2],[b])],[])
        current=VerseAlignment([AlignmentGroup([h2],[b]),AlignmentGroup([h1],[a])],[])
        reviewed_inv=make_inventory(reviewed)
        self.assertEqual(reviewed_inv.bottom_ids['T001'].word,'அ')
        current_inv=make_inventory(current)
        self.assertEqual(current_inv.bottom_ids['T001'].word,'ஆ')
        r=AICheckReview(tool='translationNotes',group_id='g',check_id='c',source_quote='x',proposed_selection_ids=['T001'],proposed_selection_text=['அ'])
        app=BridgeApp.__new__(BridgeApp); app.session=EditSession(current); app.review_alignment_for_checks=reviewed
        records=BridgeApp._selection_records_for_review(app,r)
        self.assertEqual(records,[{'text':'அ','occurrence':1,'occurrences':1}])

    def test_check_sync_rolls_back_if_index_write_fails(self):
        import tc_ai_bridge.tc_project as mod
        td,p=self.temp_project('rut')
        try:
            chosen=None
            for ch in p.chapters():
                for vs in p.verses(ch):
                    if vs=='front': continue
                    inv=make_inventory(p.load_verse_alignment(ch,vs))
                    if not inv.bottom: continue
                    for e in p.checks_for_verse(ch,vs):
                        if e.get('selections') is False:
                            chosen=(ch,vs,e,inv); break
                    if chosen: break
                if chosen: break
            ch,vs,e,inv=chosen; c=e['contextId']; index=p.index_dir/c['tool']/p.book_id/f"{c['groupId']}.json"; before=index.read_bytes(); tok=next(iter(inv.bottom_ids.values()))
            real=mod._write_json_atomic; calls={'n':0}
            def flaky(path,data):
                calls['n']+=1
                if Path(path)==index: raise OSError('simulated index failure')
                return real(path,data)
            sel_dir=p.check_dir/'selections'/p.book_id/str(ch)/str(vs); inv_dir=p.check_dir/'invalidated'/p.book_id/str(ch)/str(vs)
            before_sel={x.name for x in sel_dir.glob('*.json')} if sel_dir.exists() else set(); before_inv={x.name for x in inv_dir.glob('*.json')} if inv_dir.exists() else set()
            with patch('tc_ai_bridge.tc_project._write_json_atomic',side_effect=flaky):
                with self.assertRaises(OSError):
                    p.sync_check_approval(ch,vs,c['tool'],c['groupId'],c['checkId'],[{'text':tok.word,'occurrence':tok.occurrence,'occurrences':tok.occurrences}],False,'Tester')
            self.assertEqual(index.read_bytes(),before)
            self.assertEqual({x.name for x in sel_dir.glob('*.json')} if sel_dir.exists() else set(),before_sel)
            self.assertEqual({x.name for x in inv_dir.glob('*.json')} if inv_dir.exists() else set(),before_inv)
        finally: td.cleanup()

    def test_scripture_transaction_rolls_back_on_mid_write_failure(self):
        import tc_ai_bridge.tc_project as mod
        td,p=self.temp_project('oba')
        try:
            ch,vs='1','1'; chapter_path=p.book_dir/'1.json'; align_path=p.chapter_path('1'); before_ch=chapter_path.read_bytes(); before_align=align_path.read_bytes(); before_text=p.target_verse_text(ch,vs)
            real=mod._write_json_atomic
            def flaky(path,data):
                if Path(path)==align_path: raise OSError('simulated alignment write failure')
                return real(path,data)
            with patch('tc_ai_bridge.tc_project._write_json_atomic',side_effect=flaky):
                with self.assertRaises(OSError): p.apply_scripture_edit(ch,vs,before_text+' சோதனை','Tester',['meaning'])
            self.assertEqual(chapter_path.read_bytes(),before_ch); self.assertEqual(align_path.read_bytes(),before_align); self.assertEqual(p.target_verse_text(ch,vs),before_text)
        finally: td.cleanup()

if __name__=='__main__': unittest.main(verbosity=2)
