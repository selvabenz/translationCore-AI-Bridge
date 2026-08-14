from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from tc_ai_bridge.ai_client import OpenAIResponsesClient
from tc_ai_bridge.alignment_engine import make_inventory, unalign_bottom
from tc_ai_bridge.knowledge_base import TranslationHelpsKnowledgeBase
from tc_ai_bridge.tc_project import TranslationCoreProject, TranslationCoreRoot
from tests.fixture_utils import make_lightweight_root, find_project, find_numbered_verse

REAL_ROOT=Path(os.getenv('TC_TEST_ROOT','__missing_real_backend_fixture__'))


@unittest.skipUnless(REAL_ROOT.exists(),'real backend unavailable')
class KnowledgeBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projects={p.book_id:p for p in TranslationCoreRoot(REAL_ROOT).projects()}

    def test_project_pins_and_fallbacks(self):
        if 'rut' not in self.projects or 'psa' not in self.projects:
            self.skipTest('Ruth/Psalms fixture projects unavailable')
        rut=TranslationHelpsKnowledgeBase(self.projects['rut']).inventory()['resources']
        self.assertEqual(rut['translationNotes']['version'],'v87')
        self.assertEqual(rut['translationWords']['version'],'v87')
        self.assertTrue(rut['translationNotes']['project_pinned'])
        self.assertEqual(rut['translationAcademy']['provider'],'unfoldingWord')
        psa=TranslationHelpsKnowledgeBase(self.projects['psa']).inventory()['resources']
        self.assertEqual(psa['translationNotes']['version'],'v87')
        self.assertFalse(psa['translationNotes']['project_pinned'])

    def test_every_indexed_tc_check_has_primary_knowledge_evidence(self):
        total=0
        for p in self.projects.values():
            kb=TranslationHelpsKnowledgeBase(p)
            for ch in p.chapters():
                for vs in p.verses(ch):
                    for e in p.checks_for_verse(ch,vs):
                        total+=1
                        ctx=e.get('contextId',{})
                        kinds={x.kind for x in kb.evidence_for_check(e)}
                        if ctx.get('tool')=='translationNotes':
                            self.assertIn('translationNote',kinds,(p.book_id,ch,vs,ctx.get('groupId')))
                            self.assertIn('translationAcademy',kinds,(p.book_id,ch,vs,ctx.get('groupId')))
                        elif ctx.get('tool')=='translationWords':
                            self.assertIn('translationWords',kinds,(p.book_id,ch,vs,ctx.get('groupId')))
        self.assertGreater(total,0)

    def test_reference_bible_is_secondary_and_available_for_ruth(self):
        if 'rut' not in self.projects:
            self.skipTest('Ruth fixture project unavailable')
        kb=TranslationHelpsKnowledgeBase(self.projects['rut'])
        refs=kb.reference_bible_text('1','1')
        self.assertTrue(refs)
        self.assertTrue(all(not x.authoritative for x in refs))

    def _temp_project(self, preferred='rut'):
        src=find_project(self.projects, preferred, require_checks=True).path
        td,tc=make_lightweight_root(REAL_ROOT,[src])
        return td, TranslationCoreProject(tc/'projects'/src.name)

    def test_mock_full_review_uses_evidence_and_saves_only_companion_data(self):
        td,p=self._temp_project('rut')
        try:
            kb=TranslationHelpsKnowledgeBase(p)
            # Select a verse with at least one check and target token.
            chosen=None
            for ch in p.chapters():
                for vs in p.verses(ch):
                    if vs=='front' or not p.checks_for_verse(ch,vs): continue
                    a=p.load_verse_alignment(ch,vs)
                    if make_inventory(a).bottom:
                        chosen=(ch,vs,a); break
                if chosen: break
            self.assertIsNotNone(chosen)
            ch,vs,a=chosen
            before=sum(1 for _ in (p.path/'.apps/translationCore/checkData').rglob('*.json'))
            captured={}
            def transport(url,headers,body,timeout):
                request=json.loads(body.decode('utf-8')); sent=json.loads(request['input']); captured['sent']=sent
                checks=sent['translationCore_checks']; tamil_ids=[x['id'] for x in sent['tamil_bottomWords']]
                reviews=[{'tool':c['tool'],'group_id':c['groupId'],'check_id':c['checkId'],'source_quote':c.get('source_quote') or '',
                          'selection_ids':tamil_ids[:1],'nothing_to_select':False,'verdict':'review','severity':'medium',
                          'rationale':'Mock evidence-backed result','suggested_correction':'','confidence':0.84,
                          'evidence_ids':c.get('evidence_ids',[])[:1]} for c in checks]
                qa=[]
                if sent['evidence_catalog']:
                    qa=[{'severity':'medium','category':'consistency','title':'Mock QA','detail':'Verify context','confidence':0.8,'check_id':'','group_id':'','evidence_ids':[next(iter(sent['evidence_catalog']))]}]
                result={'summary':'Mock full review','check_reviews':reviews,'qa_issues':qa}
                return 200,json.dumps({'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}],'usage':{'total_tokens':77}}).encode('utf-8')
            client=OpenAIResponsesClient('fake','gpt-test',transport=transport)
            reviews,issues,summary,meta=client.run_full_review(p,ch,vs,a,kb)
            self.assertEqual(summary,'Mock full review'); self.assertEqual(len(reviews),len(p.checks_for_verse(ch,vs)))
            self.assertTrue(captured['sent']['evidence_catalog']); self.assertTrue(all(r.proposed_selection_text for r in reviews))
            saved=Path(meta['saved_to']); self.assertTrue(saved.exists()); self.assertIn('.apps/translationCoreAI/aiReview',saved.as_posix())
            after=sum(1 for _ in (p.path/'.apps/translationCore/checkData').rglob('*.json'))
            self.assertEqual(before,after)
        finally:
            td.cleanup()

    def test_prepare_verse_automates_alignment_then_resource_review(self):
        # Do not assume a user's Obadiah is still unaligned. Create an in-memory unaligned
        # target token from any suitable real verse so the AI-alignment path is deterministic.
        src=find_project(self.projects,'oba').path
        td,tc=make_lightweight_root(REAL_ROOT,[src])
        try:
            p=TranslationCoreProject(tc/'projects'/src.name); kb=TranslationHelpsKnowledgeBase(p)
            ch,vs,a=find_numbered_verse(p)
            baseline=p.load_verse_alignment(ch,vs).to_dict()
            inv=make_inventory(a); self.assertTrue(inv.bottom)
            a=unalign_bottom(a,[inv.bottom[0]])
            self.assertTrue(a.word_bank)
            calls=[]
            def transport(url,headers,body,timeout):
                req=json.loads(body.decode()); name=req['text']['format']['name']; calls.append(name); sent=json.loads(req['input'])
                if name=='tc_alignment_proposal':
                    # Return a COMPLETE gap-filling proposal that preserves every existing
                    # non-empty human/project alignment. Real certification backends evolve,
                    # so the mock must not assume Obadiah is still largely unaligned.
                    inv_a=make_inventory(a)
                    groups=[]; attached=set(); first_group=None
                    for existing in a.alignments:
                        if not existing.top_words:
                            continue
                        hids=[inv_a.top_sig_to_id[x.signature] for x in existing.top_words]
                        tids=[inv_a.bottom_sig_to_id[x.signature] for x in existing.bottom_words]
                        attached.update(tids)
                        rec={'top_ids':hids,'bottom_ids':tids,'confidence':.95,'reason':'mock preserve/fill'}
                        groups.append(rec)
                        if first_group is None:
                            first_group=rec
                    self.assertIsNotNone(first_group)
                    # Attach every currently unaligned Tamil token to an existing source group
                    # so the automatic-preparation path demonstrably reduces the word bank.
                    extras=[x['id'] for x in sent['tamil_bottomWords'] if x['id'] not in attached]
                    first_group['bottom_ids'].extend(extras)
                    result={'groups':groups,'review_notes':['mock']}
                else:
                    reviews=[]
                    for c in sent['translationCore_checks']:
                        reviews.append({'tool':c['tool'],'group_id':c['groupId'],'check_id':c['checkId'],'source_quote':c.get('source_quote') or '',
                                        'selection_ids':[sent['tamil_bottomWords'][0]['id']],'nothing_to_select':False,'verdict':'review','severity':'medium',
                                        'rationale':'mock','suggested_correction':'','confidence':.8,'evidence_ids':c.get('evidence_ids',[])[:1]})
                    result={'summary':'prepared','check_reviews':reviews,'qa_issues':[]}
                return 200,json.dumps({'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}],'usage':{'total_tokens':31}}).encode()
            client=OpenAIResponsesClient('fake','gpt-test',transport=transport)
            proposal,reviewed,reviews,issues,summary,meta=client.prepare_verse_review(p,ch,vs,a,kb)
            self.assertEqual(calls,['tc_alignment_proposal','tc_full_review']); self.assertIsNotNone(proposal); self.assertEqual(summary,'prepared')
            self.assertLess(len(reviewed.word_bank),len(a.word_bank)); self.assertIsNotNone(json.loads(Path(meta['saved_to']).read_text(encoding='utf-8-sig')).get('alignmentProposal'))
            # The on-disk alignment remains exactly the pre-review project state; AI preparation never writes it.
            self.assertEqual(baseline, p.load_verse_alignment(ch,vs).to_dict())
        finally:
            td.cleanup()

    def test_full_review_missing_check_becomes_explicit_review_item(self):
        td,p=self._temp_project('rut')
        try:
            kb=TranslationHelpsKnowledgeBase(p)
            chosen=None
            for ch in p.chapters():
                for vs in p.verses(ch):
                    if vs!='front' and p.checks_for_verse(ch,vs):
                        a=p.load_verse_alignment(ch,vs)
                        if make_inventory(a).bottom: chosen=(ch,vs,a); break
                if chosen: break
            ch,vs,a=chosen
            def transport(url,headers,body,timeout):
                sent=json.loads(json.loads(body.decode())['input']); reviews=[]
                if sent['translationCore_checks']:
                    c=sent['translationCore_checks'][0]
                    reviews=[{'tool':c['tool'],'group_id':c['groupId'],'check_id':c['checkId'],'source_quote':c.get('source_quote') or '',
                              'selection_ids':[],'nothing_to_select':True,'verdict':'review','severity':'medium','rationale':'mock','suggested_correction':'','confidence':.7,'evidence_ids':c.get('evidence_ids',[])[:1]}]
                result={'summary':'partial model result','check_reviews':reviews,'qa_issues':[]}
                return 200,json.dumps({'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}).encode()
            client=OpenAIResponsesClient('fake','gpt-test',transport=transport)
            reviews,issues,summary,meta=client.run_full_review(p,ch,vs,a,kb); expected=len(p.checks_for_verse(ch,vs))
            self.assertEqual(len(reviews),expected); omitted=[r for r in reviews if r.confidence==0.0 and 'omitted' in r.rationale.lower()]
            self.assertEqual(len(omitted),max(0,expected-1)); self.assertTrue(Path(meta['saved_to']).exists())
        finally:
            td.cleanup()

    def test_full_review_rejects_fabricated_selection_id(self):
        p=find_project(self.projects,'rut',require_checks=True); kb=TranslationHelpsKnowledgeBase(p)
        chosen=None
        for ch in p.chapters():
            for vs in p.verses(ch):
                if vs!='front' and p.checks_for_verse(ch,vs):
                    a=p.load_verse_alignment(ch,vs)
                    if make_inventory(a).bottom: chosen=(ch,vs,a); break
            if chosen: break
        ch,vs,a=chosen
        def transport(url,headers,body,timeout):
            sent=json.loads(json.loads(body.decode())['input']); c=sent['translationCore_checks'][0]
            result={'summary':'bad','check_reviews':[{'tool':c['tool'],'group_id':c['groupId'],'check_id':c['checkId'],'source_quote':c.get('source_quote') or '',
                    'selection_ids':['T999999'],'nothing_to_select':False,'verdict':'problem','severity':'high','rationale':'bad','suggested_correction':'','confidence':.9,'evidence_ids':[]}],'qa_issues':[]}
            return 200,json.dumps({'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}).encode()
        client=OpenAIResponsesClient('fake','gpt-test',transport=transport)
        with self.assertRaises(Exception): client.run_full_review(p,ch,vs,a,kb)

if __name__=='__main__': unittest.main(verbosity=2)
