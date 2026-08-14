from __future__ import annotations

import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os

from tc_ai_bridge.alignment_engine import make_inventory
from tc_ai_bridge.models import AICheckReview, QAIssue
from tc_ai_bridge.ui import BridgeApp

ROOT=os.getenv('TC_TEST_ROOT','__missing_real_backend_fixture__')


def pump(app: BridgeApp, timeout: float = 8.0):
    end=time.time()+timeout
    while app._busy and time.time()<end:
        app.update(); time.sleep(0.01)
    app.update()
    if app._busy:
        raise AssertionError('background UI operation did not finish')


class MockReviewClient:
    def __init__(self):
        self.calls=[]
        class U: total_tokens=73
        self.last_usage=U()
    def prepare_verse_review(self, project, ch, vs, alignment, kb, progress_callback=None):
        self.calls.append((ch,vs))
        if progress_callback:
            for pct,msg in [(5,'start'),(38,'alignment ready'),(58,'evidence'),(88,'validating'),(100,'complete')]:
                progress_callback(pct,msg)
        inv=make_inventory(alignment)
        proposal=None
        if inv.top and inv.bottom:
            proposal={'groups':[{'top_ids':['H001'],'bottom_ids':['T001'],'confidence':.95,'reason':'mock UI alignment'}],'review_notes':['mock review note']}
        reviews=[AICheckReview(tool='translationNotes',group_id='figs-metaphor',check_id='mock-check',source_quote='mock',proposed_selection_ids=['T001'] if inv.bottom else [],proposed_selection_text=[inv.bottom[0].word] if inv.bottom else [],nothing_to_select=not bool(inv.bottom),verdict='review',severity='medium',rationale='mock evidence-backed review',suggested_correction='',confidence=.91,evidence_used=[{'title':'Mock Translation Note','kind':'translationNote','version':'v87','provider':'unfoldingWord','content':'mock evidence'}])]
        issues=[QAIssue(code='AI_TEST',severity='medium',title='Mock QA',detail='mock detail',source='OpenAI+KnowledgeBase',confidence=.8)]
        return proposal, alignment, reviews, issues, 'Mock full review complete', {'total_tokens_for_prepare':73,'saved_to':'/tmp/mock.json'}


@unittest.skipUnless(Path(ROOT).exists(),'real backend unavailable')
class UIWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=BridgeApp(settings_path=Path(self.tmp.name)/'settings.json')
        self.app.withdraw(); self.app.load_root(ROOT); self.app.update()
    def tearDown(self):
        if self.app.winfo_exists():
            if self.app.session: self.app.session.mark_saved()
            self.app.destroy()
        self.tmp.cleanup()

    def test_full_review_button_runs_background_lifecycle_and_populates_results(self):
        client=MockReviewClient(); self.app._get_client=lambda:client
        self.app._run_full_review(); self.assertTrue(self.app._busy)
        pump(self.app)
        self.assertEqual(len(client.calls),1)
        self.assertTrue(self.app.ai_check_reviews)
        self.assertTrue(self.app.ai_issues)
        self.assertIsNotNone(self.app.pending_ai_proposal)
        self.assertIn('mock UI alignment',self.app.ai_preview.get('1.0','end'))
        self.assertIn('complete',self.app.status_var.get().lower())
        self.assertEqual(self.app._api_state,'connected')

    def test_batch_review_button_runs_every_numbered_verse_and_progress_finishes(self):
        client=MockReviewClient(); self.app._get_client=lambda:client
        expected=len([v for v in self.app.project.verses(self.app.chapter_var.get()) if v!='front'])
        with patch('tc_ai_bridge.ui.messagebox.askyesno',return_value=True):
            self.app._run_chapter_review()
        self.assertTrue(self.app._busy); pump(self.app,20)
        self.assertEqual(len(client.calls),expected)
        self.assertIn('batch complete',self.app.review_summary_var.get().lower())
        self.assertIn('complete',self.app.status_var.get().lower())

    def test_decision_resets_alignment_preview_and_result_evidence(self):
        client=MockReviewClient(); self.app._get_client=lambda:client
        self.app._run_full_review(); pump(self.app)
        self.app.review_tree.selection_set('0'); self.app._review_selected()
        self.assertTrue(self.app.review_detail.get('1.0','end').strip())
        self.app.project.record_human_decision=lambda *a,**k: Path(self.tmp.name)/'decision.json'
        self.app.project.sync_check_approval=lambda *a,**k: {'index':'mock'}
        self.app.project.rebase_ai_review_fingerprint=lambda *a,**k: None
        self.app._record_review_decision('accepted'); self.app.update()
        self.assertIsNone(self.app.pending_ai_proposal)
        self.assertEqual(self.app.ai_preview.get('1.0','end').strip(),'')
        self.assertEqual(self.app.review_detail.get('1.0','end').strip(),'')
        self.assertEqual(str(self.app.apply_ai_btn['state']),'disabled')

    def test_proposal_pane_is_user_resizable_panedwindow_child(self):
        # The AI preview is nested under a vertical ttk.Panedwindow so the user can drag its sash.
        parent=self.app.ai_preview.master.master.master
        self.assertEqual(parent.winfo_class(),'TPanedwindow')
        self.assertEqual(str(parent.cget('orient')),'vertical')


    def test_batch_continues_after_one_verse_failure(self):
        class FailingClient(MockReviewClient):
            def prepare_verse_review(self, project, ch, vs, alignment, kb, progress_callback=None):
                if len(self.calls)==1:
                    self.calls.append((ch,vs)); raise RuntimeError('mock verse failure')
                return super().prepare_verse_review(project,ch,vs,alignment,kb,progress_callback)
        client=FailingClient(); self.app._get_client=lambda:client
        expected=len([v for v in self.app.project.verses(self.app.chapter_var.get()) if v!='front'])
        with patch('tc_ai_bridge.ui.messagebox.askyesno',return_value=True):
            self.app._run_chapter_review()
        pump(self.app,20)
        self.assertEqual(len(client.calls),expected)
        self.assertIn('failed',self.app.review_summary_var.get().lower())
        self.assertFalse(self.app._busy)

    def test_all_three_human_decisions_reset_transient_panels(self):
        for decision in ('accepted','needs_discussion','rejected'):
            client=MockReviewClient(); self.app._get_client=lambda client=client:client
            self.app._run_full_review(); pump(self.app)
            self.app.review_tree.selection_set('0'); self.app._review_selected()
            self.app.project.record_human_decision=lambda *a,**k: Path(self.tmp.name)/f'{decision}.json'
            self.app.project.sync_check_approval=lambda *a,**k: {'index':'mock'}
            self.app.project.rebase_ai_review_fingerprint=lambda *a,**k: None
            self.app._record_review_decision(decision); self.app.update()
            self.assertIsNone(self.app.pending_ai_proposal)
            self.assertEqual(self.app.ai_preview.get('1.0','end').strip(),'')
            self.assertEqual(self.app.review_detail.get('1.0','end').strip(),'')

    def test_api_green_indicator_after_successful_probe(self):
        class Conn:
            model='gpt-5.6'
            def test_connection(self): return {'id':'gpt-5.6','object':'model'}
        self.app.api_key_var.set('fake-key'); self.app.persist_key_var.set(False)
        with patch('tc_ai_bridge.ui.OpenAIResponsesClient',return_value=Conn()):
            self.app._test_api_connection(silent=True); pump(self.app)
        self.assertEqual(self.app._api_state,'connected')
        self.assertIn('Connected',self.app.api_status_var.get())

if __name__=='__main__': unittest.main(verbosity=2)
