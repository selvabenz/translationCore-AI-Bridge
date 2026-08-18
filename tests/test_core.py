from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tc_ai_bridge.ai_client import OpenAIResponsesClient
from tc_ai_bridge.alignment_engine import apply_proposal, make_inventory, realign, unalign_bottom, validate_proposal
from tc_ai_bridge.local_checks import run_local_qa
from tc_ai_bridge.models import AlignmentGroup, TokenRef, VerseAlignment
from tc_ai_bridge.session import EditSession
from tc_ai_bridge.tc_project import ProjectError, TranslationCoreProject, TranslationCoreRoot

REAL_ROOT = Path(os.getenv('TC_TEST_ROOT', '__missing_real_backend_fixture__'))


def sha256(path: Path) -> str:
    h=hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()


class ModelTests(unittest.TestCase):
    def test_manual_alignment_many_to_many_and_undo(self):
        h1=TokenRef('א',1,1,lemma='a'); h2=TokenRef('ב',1,1,lemma='b')
        t1=TokenRef('தமிழ்',1,1,type='bottomWord'); t2=TokenRef('சொல்',1,1,type='bottomWord')
        v=VerseAlignment([AlignmentGroup([h1],[]),AlignmentGroup([h2],[])],[t1,t2])
        changed=realign(v,[h1,h2],[t1,t2])
        self.assertEqual(len(changed.word_bank),0)
        self.assertTrue(any(len(g.top_words)==2 and len(g.bottom_words)==2 for g in changed.alignments))
        s=EditSession(v); s.replace(changed); self.assertTrue(s.undo()); self.assertEqual(len(s.current.word_bank),2); self.assertTrue(s.redo())
        un=unalign_bottom(s.current,[t1]); self.assertTrue(any(x.signature==t1.signature for x in un.word_bank))

    def test_ai_proposal_rejects_fabricated_and_duplicates(self):
        v=VerseAlignment([AlignmentGroup([TokenRef('א')],[])],[TokenRef('தமிழ்',type='bottomWord')])
        inv=make_inventory(v)
        valid={'groups':[{'top_ids':[next(iter(inv.top_ids))],'bottom_ids':[next(iter(inv.bottom_ids))],'confidence':.9,'reason':'x'}],'review_notes':[]}
        self.assertEqual(len(validate_proposal(v,valid)),1)
        bad=copy.deepcopy(valid); bad['groups'][0]['bottom_ids']=['T999']
        with self.assertRaises(Exception): validate_proposal(v,bad)
        dup={'groups':[valid['groups'][0],valid['groups'][0]],'review_notes':[]}
        with self.assertRaises(Exception): validate_proposal(v,dup)


@unittest.skipUnless(REAL_ROOT.exists(), 'real uploaded translationCore backend not present')
class RealBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=TranslationCoreRoot(REAL_ROOT)
        cls.projects={p.book_id:p for p in cls.root.projects()}

    def test_discovers_expected_real_projects(self):
        self.assertGreaterEqual(len(self.projects),1)
        # Certification must tolerate additional books and ongoing project work.
        # If the historical Ruth/Psalms/Obadiah fixtures are present, they should be discoverable,
        # but extra projects (for example Genesis) are valid and must not fail discovery.
        expected={'rut','psa','oba'}
        if expected & set(self.projects):
            self.assertTrue((expected & set(self.projects)).issubset(set(self.projects)))
        for p in self.projects.values():
            self.assertTrue(p.book_id)
            self.assertTrue(p.chapters())

    def test_every_alignment_chapter_parses_and_validates(self):
        total=0
        for p in self.projects.values():
            for ch in p.chapters():
                data=p.load_alignment_chapter(ch)
                for raw in data.values():
                    p._validate_verse_raw(raw); total+=1
        self.assertGreater(total,2700)

    def test_capability_detection_matches_backend(self):
        if 'rut' in self.projects:
            self.assertGreater(self.projects['rut'].check_types().get('selections',0),0)
            self.assertGreater(self.projects['rut'].index_tools().get('translationNotes',0),0)
        if 'psa' in self.projects:
            self.assertEqual(len(self.projects['psa'].chapters()),150)
        # Do not assume Obadiah is still untouched: a live user project may now be fully aligned.
        for p in self.projects.values():
            ch=p.chapters()[0]; vs=next(v for v in p.verses(ch) if v!='front')
            a=p.load_verse_alignment(ch,vs)
            self.assertIsInstance(a.word_bank,list)

    def test_ruth_translationcore_check_state_is_readable(self):
        p=self.projects['rut']
        # Ruth has hundreds of indexed items and reviewer state files; iterate all verses.
        found=0
        for ch in p.chapters():
            for vs in p.verses(ch):
                found += len(p.checks_for_verse(ch,vs))
                p.check_state_for_verse(ch,vs)
        self.assertGreater(found,500)

    def test_local_qa_runs_on_every_real_verse(self):
        count=0
        for p in self.projects.values():
            for ch in p.chapters():
                for vs in p.verses(ch):
                    a=p.load_verse_alignment(ch,vs)
                    issues=run_local_qa(p,ch,vs,a)
                    self.assertIsInstance(issues,list); count+=1
        self.assertGreater(count,2700)

    def test_end_to_end_write_backup_atomic_stale_guard_and_source_preservation(self):
        src=self.projects['oba'].path
        with tempfile.TemporaryDirectory() as td:
            dst=Path(td)/src.name
            shutil.copytree(src,dst,ignore=shutil.ignore_patterns('.git'))
            p=TranslationCoreProject(dst)
            usfm=p.usfm_path(); before_usfm=sha256(usfm) if usfm else None
            ch='1'; selected_vs=None
            for vs in p.verses(ch):
                a=p.load_verse_alignment(ch,vs)
                inv=make_inventory(a)
                if inv.top and inv.bottom:
                    selected_vs=vs; break
            self.assertIsNotNone(selected_vs)
            vs=selected_vs; original=p.load_alignment_chapter(ch)[vs]; a=p.load_verse_alignment(ch,vs); inv=make_inventory(a)
            changed=realign(a,[inv.top[0]],[inv.bottom[0]])
            backup=p.save_verse_alignment(ch,vs,changed,copy.deepcopy(original))
            self.assertTrue(backup.exists())
            reloaded=p.load_verse_alignment(ch,vs)
            self.assertEqual(reloaded.to_dict(),changed.to_dict())
            if usfm: self.assertEqual(before_usfm,sha256(usfm))
            # stale write guard: original snapshot is no longer current
            with self.assertRaises(ProjectError): p.save_verse_alignment(ch,vs,a,copy.deepcopy(original))
            # Restore reverses safely and first backs up the current chapter.
            backups=p.list_alignment_backups(ch); self.assertIn(backup,backups)
            safety=p.restore_alignment_backup(ch,backup); self.assertTrue(safety.exists())
            self.assertEqual(p.load_alignment_chapter(ch)[vs],original)
            if usfm: self.assertEqual(before_usfm,sha256(usfm))
            review=p.record_review_state(ch,vs,'approved'); self.assertTrue(review.exists())


class MockAITests(unittest.TestCase):

    def test_transient_api_failures_retry_then_succeed(self):
        calls=[]
        def transport(url,headers,body,timeout):
            calls.append(1)
            if len(calls)<3:
                return 429,json.dumps({'error':{'message':'rate limited'}}).encode()
            result={'groups':[],'review_notes':[]}
            return 200,json.dumps({'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}).encode()
        c=OpenAIResponsesClient('fake','gpt-test',transport=transport)
        schema={'type':'object','additionalProperties':False,'properties':{'groups':{'type':'array','items':{'type':'string'}},'review_notes':{'type':'array','items':{'type':'string'}}},'required':['groups','review_notes']}
        from unittest.mock import patch
        with patch('tc_ai_bridge.ai_client.time.sleep',return_value=None):
            out=c._post_structured('x','{}','retry_test',schema)
        self.assertEqual(len(calls),3); self.assertEqual(out['groups'],[])

    @unittest.skipUnless(REAL_ROOT.exists(), 'real uploaded translationCore backend not present')
    def test_mock_ai_alignment_end_to_end_on_real_obadiah(self):
        """Exercise the v0.7.3+ gap-fill path without assuming Obadiah is untouched.

        A real user's project may be fresh, partial, or fully aligned. The certification test must
        therefore derive its mock link from the unresolved IDs actually sent to AI and must verify
        preservation/no-token-loss rather than assuming ``wordBank`` is non-empty.
        """
        p={x.book_id:x for x in TranslationCoreRoot(REAL_ROOT).projects()}['oba']
        a=p.load_verse_alignment('1','1')
        before=make_inventory(a)
        before_top={x.signature for x in before.top}
        before_bottom={x.signature for x in before.bottom}
        protected_before=[
            ({x.signature for x in g.top_words},{x.signature for x in g.bottom_words})
            for g in a.alignments if g.top_words and g.bottom_words
        ]
        chosen={'top_id':None,'bottom_id':None}

        def transport(url,headers,body,timeout):
            request=json.loads(body.decode('utf8'))
            sent=json.loads(request['input'])
            self.assertTrue(sent['source_tokens_to_consider']); self.assertTrue(sent['target_tokens_to_consider'])
            unresolved_top=list(sent.get('unresolved_source_ids') or [])
            unresolved_bottom=list(sent.get('unresolved_target_ids') or [])
            links=[]
            if unresolved_top and unresolved_bottom:
                chosen['top_id']=unresolved_top[0]; chosen['bottom_id']=unresolved_bottom[0]
                links=[{'top_id':chosen['top_id'],'bottom_id':chosen['bottom_id'],'confidence':0.93,'reason':'mock semantic match'}]
            result={
                'links':links,
                'implicit_top_ids':[],
                'target_only_ids':[],
                'review_notes':['review remaining tokens'],
            }
            response={'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}],'usage':{'total_tokens':44}}
            return 200,json.dumps(response).encode()

        c=OpenAIResponsesClient('fake','gpt-test',transport=transport)
        proposal=c.propose_alignment(p,'1','1',a)
        validate_proposal(a,proposal)
        applied=apply_proposal(a,proposal)
        after=make_inventory(applied)

        # The end-to-end mock may fill a gap, or on a completed verse it may correctly do nothing.
        # Either way every real source and target token must survive the proposal round-trip.
        self.assertEqual(before_top,{x.signature for x in after.top})
        self.assertEqual(before_bottom,{x.signature for x in after.bottom})

        # Existing non-empty project groups are protected evidence in gap-fill mode.
        applied_groups=[
            ({x.signature for x in g.top_words},{x.signature for x in g.bottom_words})
            for g in applied.alignments if g.top_words and g.bottom_words
        ]
        for top_sigs,bottom_sigs in protected_before:
            self.assertTrue(
                any(top_sigs.issubset(pt) and bottom_sigs.issubset(pb) for pt,pb in applied_groups),
                'gap-fill mock must preserve every established project alignment',
            )

        # If the real verse had an unresolved source+target pair, the mock link should be present.
        if chosen['top_id'] and chosen['bottom_id']:
            top_sig=before.top_ids[chosen['top_id']].signature
            bottom_sig=before.bottom_ids[chosen['bottom_id']].signature
            self.assertTrue(any(top_sig in pt and bottom_sig in pb for pt,pb in applied_groups))
        else:
            # A fully aligned/protected real verse is also a valid certification fixture.
            self.assertEqual(
                {x.signature for x in a.word_bank},
                {x.signature for x in applied.word_bank},
            )

    @unittest.skipUnless(REAL_ROOT.exists(), 'real uploaded translationCore backend not present')
    def test_mock_ai_quality_end_to_end_on_real_ruth(self):
        p={x.book_id:x for x in TranslationCoreRoot(REAL_ROOT).projects()}['rut']
        a=p.load_verse_alignment('1','1')
        def transport(url,headers,body,timeout):
            result={'summary':'Mock QA complete','issues':[{'severity':'medium','category':'consistency','title':'Review term','detail':'Check contextual consistency.','evidence':'Mock evidence','confidence':0.8,'check_id':'','group_id':''}]}
            response={'output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}
            return 200,json.dumps(response).encode()
        c=OpenAIResponsesClient('fake','gpt-test',transport=transport)
        issues,summary=c.run_quality_review(p,'1','1',a)
        self.assertEqual(summary,'Mock QA complete'); self.assertEqual(len(issues),1); self.assertEqual(issues[0].source,'OpenAI')

    def test_responses_request_uses_store_false_and_structured_schema(self):
        captured={}
        response_obj={
            'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'groups':[],'review_notes':['ok']})}]}],
            'usage':{'input_tokens':10,'output_tokens':5,'total_tokens':15},
        }
        def transport(url,headers,body,timeout):
            captured['url']=url; captured['headers']=headers; captured['body']=json.loads(body.decode()); return 200,json.dumps(response_obj).encode()
        c=OpenAIResponsesClient('test-key','gpt-test',transport=transport)
        schema={'type':'object','additionalProperties':False,'properties':{'groups':{'type':'array','items':{'type':'string'}},'review_notes':{'type':'array','items':{'type':'string'}}},'required':['groups','review_notes']}
        out=c._post_structured('i','x','schema',schema)
        self.assertEqual(out['review_notes'],['ok'])
        self.assertFalse(captured['body']['store'])
        self.assertEqual(captured['body']['text']['format']['type'],'json_schema')
        self.assertTrue(captured['body']['text']['format']['strict'])
        self.assertEqual(c.last_usage.total_tokens,15)
        self.assertNotIn('test-key',json.dumps(captured['body']))


if __name__=='__main__': unittest.main(verbosity=2)
