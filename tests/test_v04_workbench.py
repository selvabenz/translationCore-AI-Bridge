from __future__ import annotations

import copy
import os
import shutil
import tempfile
import time
import unittest
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from unittest.mock import Mock, patch

from tc_ai_bridge.alignment_engine import make_inventory, realign
from tc_ai_bridge.tc_project import TranslationCoreProject, TranslationCoreRoot
from tc_ai_bridge.ui import BridgeApp

ROOT = Path(os.getenv('TC_TEST_ROOT', '__missing_real_backend_fixture__'))


def pump(app: BridgeApp, timeout: float = 8.0):
    end = time.time() + timeout
    while app._busy and time.time() < end:
        app.update(); time.sleep(0.01)
    app.update()
    if app._busy:
        raise AssertionError('background UI operation did not finish')


@unittest.skipUnless(ROOT.exists(), 'real backend unavailable')
class ProjectStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projects = {p.book_id: p for p in TranslationCoreRoot(ROOT).projects()}

    def test_project_scan_classifies_real_projects(self):
        oba = self.projects['oba'].project_scan()
        rut = self.projects['rut'].project_scan()
        psa = self.projects['psa'].project_scan()
        self.assertEqual(oba['verses'], 21)
        self.assertEqual(psa['verses'], 2461)
        self.assertEqual(rut['verses'], 85)
        self.assertGreater(rut['translationNotes']['checked'], 200)
        self.assertGreater(rut['translationWords']['checked'], 150)
        self.assertGreater(psa['alignment']['untouched'], 2000)
        self.assertEqual(sum(psa['aiReview'].values()), psa['verses'])

    def test_review_fingerprint_marks_alignment_change_stale_but_human_decision_does_not(self):
        src = self.projects['oba'].path
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / src.name
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns('.git'))
            p = TranslationCoreProject(dst)
            ch, vs = '1', '1'
            p.record_ai_review_result(ch, vs, {'summary': 'cached', 'checkReviews': [], 'qaIssues': []})
            self.assertEqual(p.ai_review_cache_status(ch, vs), 'current')
            p.record_human_decision(ch, vs, 'c1', 'accepted', selection_text=['x'])
            self.assertEqual(p.ai_review_cache_status(ch, vs), 'current')
            a = p.load_verse_alignment(ch, vs); inv = make_inventory(a)
            changed = realign(a, [inv.top[0]], [inv.bottom[0]])
            original = copy.deepcopy(p.load_alignment_chapter(ch)[vs])
            p.save_verse_alignment(ch, vs, changed, original)
            self.assertEqual(p.ai_review_cache_status(ch, vs), 'stale')

    def test_human_decision_keeps_append_only_audit_history(self):
        src = self.projects['oba'].path
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / src.name
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns('.git'))
            p = TranslationCoreProject(dst)
            p.record_human_decision('1', '1', 'same-check', 'accepted', selection_ids=['T001'], model='mock')
            time.sleep(0.002)
            p.record_human_decision('1', '1', 'same-check', 'rejected', model='mock')
            latest = p.decisions_for_verse('1', '1')
            self.assertEqual(len(latest), 1)
            self.assertEqual(latest[0]['decision'], 'rejected')
            audit = list((p.companion_dir() / 'audit' / p.book_id / '1' / '1').glob('*same-check.json'))
            self.assertEqual(len(audit), 2)


class DummyBatchClient:
    def __init__(self):
        self.calls = []
        class U: total_tokens = 0
        self.last_usage = U()
    def prepare_verse_review(self, project, ch, vs, alignment, kb, progress_callback=None):
        self.calls.append((ch, vs))
        if progress_callback: progress_callback(100, 'done')
        return None, alignment, [], [], 'done', {'total_tokens_for_prepare': 0}


@unittest.skipUnless(ROOT.exists(), 'real backend unavailable')
class UIv04Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = BridgeApp(settings_path=Path(self.tmp.name)/'settings.json')
        self.app.withdraw(); self.app.load_root(str(ROOT)); self.app.update()
    def tearDown(self):
        if self.app.winfo_exists():
            if self.app.session: self.app.session.mark_saved()
            self.app.destroy()
        self.tmp.cleanup()

    def test_non_ai_background_job_never_turns_api_green(self):
        self.app._set_api_indicator('unknown', 'API not tested')
        self.app._background('Local scan', lambda: {'ok': True}, lambda r: None, ai_operation=False)
        pump(self.app)
        self.assertEqual(self.app._api_state, 'unknown')

    def test_changed_only_batch_skips_current_cached_verses(self):
        client = DummyBatchClient(); self.app._get_client = lambda: client
        verses = [v for v in self.app.project.verses(self.app.chapter_var.get()) if v != 'front']
        current = verses[0]
        original_status = self.app.project.ai_review_cache_status
        self.app.project.ai_review_cache_status = lambda ch, vs: 'current' if str(vs) == str(current) else 'missing'
        try:
            with patch('tc_ai_bridge.ui.messagebox.askyesno', return_value=True):
                self.app._run_chapter_review(force=False)
            pump(self.app, 20)
            self.assertEqual(len(client.calls), len(verses)-1)
            self.assertIn('unchanged skipped', self.app.review_summary_var.get())
        finally:
            self.app.project.ai_review_cache_status = original_status

    def test_force_batch_does_not_skip_current_cached_verses(self):
        client = DummyBatchClient(); self.app._get_client = lambda: client
        verses = [v for v in self.app.project.verses(self.app.chapter_var.get()) if v != 'front']
        original_status = self.app.project.ai_review_cache_status
        self.app.project.ai_review_cache_status = lambda ch, vs: 'current'
        try:
            with patch('tc_ai_bridge.ui.messagebox.askyesno', return_value=True):
                self.app._run_chapter_review(force=True)
            pump(self.app, 20)
            self.assertEqual(len(client.calls), len(verses))
        finally:
            self.app.project.ai_review_cache_status = original_status

    def test_edit_selection_can_only_choose_existing_bottomword_ids(self):
        from tc_ai_bridge.models import AICheckReview
        inv = make_inventory(self.app.session.current)
        ids = list(inv.bottom_ids)
        self.assertGreaterEqual(len(ids), 2)
        self.app.ai_check_reviews = [AICheckReview(tool='translationNotes', group_id='mock', check_id='edit-check', source_quote='x', proposed_selection_ids=[ids[0]], proposed_selection_text=[inv.bottom_ids[ids[0]].word], rationale='mock')]
        self.app._refresh_review_tree(); self.app.review_tree.selection_set('0')
        self.app._edit_review_selection(); self.app.update()
        wins=[w for w in self.app.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertTrue(wins); win=wins[-1]
        def walk(widget):
            out=[]
            for child in widget.winfo_children():
                out.append(child); out.extend(walk(child))
            return out
        widgets=walk(win); lb=next(w for w in widgets if isinstance(w, tk.Listbox)); use=next(w for w in widgets if isinstance(w, ttk.Button) and w.cget('text')=='Use Selected')
        lb.selection_clear(0,'end'); lb.selection_set(1); use.invoke(); self.app.update()
        self.assertEqual(self.app.ai_check_reviews[0].proposed_selection_ids,[ids[1]])
        self.assertEqual(self.app.ai_check_reviews[0].proposed_selection_text,[inv.bottom_ids[ids[1]].word])

    def test_final_approval_can_be_cancelled_when_ai_review_is_missing(self):
        original_status=self.app.project.ai_review_cache_status; original_record=self.app.project.record_review_state
        self.app.project.ai_review_cache_status=lambda ch,vs:'missing'; recorder=Mock(); self.app.project.record_review_state=recorder
        try:
            with patch('tc_ai_bridge.ui.messagebox.askyesno', return_value=False):
                self.app._approve()
            recorder.assert_not_called()
            self.assertIn('cancelled', self.app.status_var.get().lower())
        finally:
            self.app.project.ai_review_cache_status=original_status; self.app.project.record_review_state=original_record


if __name__ == '__main__':
    unittest.main(verbosity=2)
