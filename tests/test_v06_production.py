from __future__ import annotations

import json, os, shutil, subprocess, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

from tc_ai_bridge.analytics import translation_words_book_analytics, exception_first_queue
from tc_ai_bridge.cache_engine import stale_reasons, dependency_snapshot
from tc_ai_bridge.git_service import GitService
from tc_ai_bridge.knowledge_base import TranslationHelpsKnowledgeBase
from tc_ai_bridge.metrics import MetricsStore
from tc_ai_bridge.model_router import ModelRouter, estimate_cost
from tc_ai_bridge.plugins import PluginRegistry
from tc_ai_bridge.psalms_qa import analyze_psalm_chapter
from tc_ai_bridge.reporting import ReportService
from tc_ai_bridge.security import redact_text, scan_tree_for_secrets, ai_payload_manifest
from tc_ai_bridge.secret_store import AppSettings
from tc_ai_bridge.team import TeamWorkflow
from tc_ai_bridge.tc_project import TranslationCoreProject, TranslationCoreRoot
from tc_ai_bridge.transaction_journal import TransactionJournal
from tc_ai_bridge.ui import BridgeApp
from tests.fixture_utils import make_lightweight_root

ROOT=Path(os.getenv('TC_TEST_ROOT','__missing_real_backend_fixture__'))
RUTH=ROOT/'projects'/'ta_ntb_rut_book'
PSA=ROOT/'projects'/'ta_ntb_psa_book'
APP_ROOT=Path(__file__).resolve().parents[1]

class ProductionPortableTests(unittest.TestCase):
    def test_model_router_and_cost_controls(self):
        self.assertEqual(ModelRouter('balanced').choose('alignment').model,'gpt-5.6-luna')
        self.assertEqual(ModelRouter('balanced').choose('final_review').model,'gpt-5.6-sol')
        self.assertEqual(ModelRouter('economy').choose('final_review').model,'gpt-5.6-terra')
        self.assertEqual(ModelRouter('quality').choose('spelling').model,'gpt-5.6-sol')
        self.assertGreater(estimate_cost('gpt-5.6-sol',1000,100),0)
        self.assertLess(estimate_cost('gpt-5.6-luna',1000,100),estimate_cost('gpt-5.6-sol',1000,100))

    def test_crash_journal_recovers_interrupted_write(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'project'; root.mkdir(); companion=root/'.apps'/'translationCoreAI'; f=root/'value.json'; f.write_text('{"v":1}\n','utf-8')
            j=TransactionJournal(root,companion); rec=j.begin('test',[f]); j.mark_writing(rec); f.write_text('{"v":99}\n','utf-8')
            self.assertEqual(len(j.pending()),1)
            out=j.recover_all(); self.assertEqual(out[0]['status'],'recovered_rollback'); self.assertEqual(json.loads(f.read_text())['v'],1); self.assertFalse(j.pending())

    def test_git_checkpoint_history_and_diff(self):
        if not GitService.executable_available(): self.skipTest('git unavailable')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); subprocess.run(['git','init',str(p)],check=True,capture_output=True); subprocess.run(['git','-C',str(p),'config','user.email','test@example.invalid'],check=True); subprocess.run(['git','-C',str(p),'config','user.name','Test'],check=True)
            f=p/'a.txt'; f.write_text('one\n'); g=GitService(p); c=g.checkpoint('initial',author_name='Reviewer'); self.assertTrue(c); self.assertTrue(g.history())
            f.write_text('two\n'); self.assertIn('two',g.diff()); self.assertTrue(g.status().dirty)

    def test_metrics_team_plugins_and_security(self):
        with tempfile.TemporaryDirectory() as td:
            c=Path(td); m=MetricsStore(c,'rut'); m.event('ai_call',total_tokens=100,estimated_cost_usd=.01,_force_test_write=True); m.event('human_accept',_force_test_write=True); m.event('human_edit',_force_test_write=True)
            s=m.summary(); self.assertEqual(s['tokens']['total'],100); self.assertGreater(s['humanEditRate'],0)
            t=TeamWorkflow(c,'rut'); t.add_member('A','translator'); t.add_member('B','consultant'); self.assertFalse(t.can_final_approve('A','verse')); self.assertTrue(t.can_final_approve('B','verse')); t.assign(1,1,'A'); self.assertEqual(t.assignment(1,1)['assignee'],'A')
            reg=PluginRegistry(); self.assertIn('sandhi',reg.get('ta').qa_categories()); self.assertEqual(reg.get('xx').id,'generic')
            secret='sk-' + 'secret_secret_secret'; header='Authorization:' + ' Bearer ' + secret; self.assertNotIn(secret,redact_text(header))
            manifest=ai_payload_manifest('rut 1:1',{'tamil_verse':'x','hebrew_topWords':[]}); self.assertFalse(manifest['unrelatedProjectFilesSent'])


    def test_synthetic_bible_scale_root_discovery_and_31k_verse_parse(self):
        # 66 lightweight tC book projects × 475 verse entries ~= full-Bible verse scale.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'translationCore'; projects=root/'projects'; projects.mkdir(parents=True)
            raw_verse={'alignments':[],'wordBank':[]}
            for i in range(66):
                bid=f'b{i:02d}'
                pp=projects/f'book_{i:02d}'; (pp/'.apps'/'translationCore'/'alignmentData'/bid).mkdir(parents=True)
                (pp/'manifest.json').write_text(json.dumps({'project':{'id':bid,'name':f'Book {i}'},'target_language':{'id':'ta','name':'Tamil'},'tc_version':8,'tc_edit_version':'3.7.0'}),'utf-8')
                chapter={str(v):raw_verse for v in range(1,476)}
                (pp/'.apps'/'translationCore'/'alignmentData'/bid/'1.json').write_text(json.dumps(chapter),'utf-8')
            t=time.perf_counter(); discovered=TranslationCoreRoot(root).projects(); count=0
            for pr in discovered: count += len([v for v in pr.verses('1') if v!='front'])
            elapsed=time.perf_counter()-t
            self.assertEqual(len(discovered),66); self.assertEqual(count,66*475); self.assertLess(elapsed,8.0)


    def test_settings_never_persist_plaintext_api_key(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'settings.json'; st=AppSettings(path); secret='sk-'+'A'*32; st.set_api_key(secret,persist=True); st.reviewer_name='Reviewer'
            raw=path.read_text('utf-8'); self.assertNotIn(secret,raw); self.assertNotIn('_session_api_key',raw); self.assertEqual(st.get_api_key(),secret)
            if os.name!='nt': self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_windows_packaging_assets_and_release_icon_present(self):
        self.assertTrue((APP_ROOT/'assets'/'app_icon.ico').exists()); self.assertTrue((APP_ROOT/'assets'/'app_icon.png').exists())
        build=(APP_ROOT/'build_windows_exe.bat').read_text('utf-8'); self.assertIn('--icon "assets\\app_icon.ico"',build); version=(APP_ROOT/'VERSION').read_text('utf-8').strip(); self.assertIn(f'v{version}',build)
        workflow=(APP_ROOT/'.github/workflows/windows-build.yml').read_text('utf-8'); self.assertIn('windows-latest',workflow); self.assertIn('Inno Setup',workflow); self.assertIn('3.12',workflow)
        self.assertTrue((APP_ROOT/'installer'/'translationCore-AI-Bridge.iss').exists())

    def test_source_tree_contains_no_embedded_openai_secret(self):
        findings=scan_tree_for_secrets(APP_ROOT)
        self.assertEqual(findings,[],findings[:10])

class ProductionRealBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RUTH.exists(): raise unittest.SkipTest('real backend unavailable')

    def test_native_tc_comment_sync_roundtrip_on_disposable_copy(self):
        with tempfile.TemporaryDirectory() as td:
            dst=Path(td)/'rut'; shutil.copytree(RUTH,dst); p=TranslationCoreProject(dst); entry=p.checks_for_verse('1','9')[0]; ctx=entry['contextId']
            out=p.sync_comment('1','9',ctx,'Production discussion test','Tester',gateway_language_quote='test quote'); self.assertTrue(out.exists())
            rows=p.comments_for_check('1','9',str(ctx['checkId'])); self.assertTrue(any(x.get('text')=='Production discussion test' for x in rows)); self.assertEqual(rows[-1]['contextId']['checkId'],ctx['checkId'])

    def test_knowledge_base_provenance_hashes_and_dependency_staleness(self):
        p=TranslationCoreProject(RUTH); kb=TranslationHelpsKnowledgeBase(p); prov=kb.provenance_manifest(); raw=json.dumps(prov)
        self.assertIn('sha256',raw.lower()); snap=dependency_snapshot(p,'1','1',kb,'balanced'); self.assertIn('resources',snap); changed=dict(snap); changed['modelPolicy']='x'; self.assertIn('AI model-routing policy changed',stale_reasons(snap,changed))

    def test_book_terminology_analytics_and_exception_queue(self):
        p=TranslationCoreProject(RUTH); d=translation_words_book_analytics(p); self.assertGreater(d['conceptCount'],0); self.assertIn('renderings',d['concepts'][0])
        q=exception_first_queue(p); self.assertIsInstance(q,list); self.assertTrue(all('chapter' in x and 'verse' in x for x in q))


    def test_read_only_scans_do_not_create_companion_artifacts_in_fixture_backend(self):
        # Never make this assertion against the user's live/current project, which may
        # legitimately contain prior Bridge work. Build a clean disposable project and
        # prove that read-only analysis itself creates no companion state.
        candidates=[x for x in (RUTH,PSA,ROOT/'projects'/'ta_ntb_oba_book') if x.exists()]
        self.assertTrue(candidates)
        for pp in candidates:
            td,tc=make_lightweight_root(ROOT,[pp],include_companion=False)
            try:
                cp=tc/'projects'/pp.name; companion=cp/'.apps'/'translationCoreAI'
                self.assertFalse(companion.exists())
                p=TranslationCoreProject(cp)
                # Exercise representative read-only production paths.
                p.project_scan(); p.check_types(); p.index_tools()
                if p.chapters():
                    ch=p.chapters()[0]
                    for vs in p.verses(ch)[:3]:
                        p.load_verse_alignment(ch,vs); p.checks_for_verse(ch,vs); p.check_state_for_verse(ch,vs)
                TranslationHelpsKnowledgeBase(p).inventory()
                self.assertFalse(companion.exists(),f'read-only scan created companion state: {companion}')
            finally:
                td.cleanup()

    def test_psalms_specialized_qa_and_report_export(self):
        p=TranslationCoreProject(PSA); d=analyze_psalm_chapter(p,'1'); self.assertEqual(d['bookId'],'psa'); self.assertIn('repeatedHebrewLemmas',d); self.assertIn('method',d)
        with tempfile.TemporaryDirectory() as td:
            out=ReportService(p).export(Path(td)); self.assertTrue(Path(out['json']).exists()); self.assertTrue(Path(out['csv']).exists()); self.assertTrue(Path(out['html']).exists()); self.assertIn('Translation QA',Path(out['html']).read_text('utf-8'))

    def test_book_scale_index_materialization_is_fast_and_stable(self):
        p=TranslationCoreProject(PSA); t=time.perf_counter(); total=0
        for ch in p.chapters():
            for vs in p.verses(ch):
                if vs!='front': total+=len(p.checks_for_verse(ch,vs))
        elapsed=time.perf_counter()-t
        self.assertGreaterEqual(total,0); self.assertIsNotNone(p._checks_by_verse_cache)
        # A second pass should be pure dictionary lookup and comfortably interactive.
        t2=time.perf_counter();
        for ch in p.chapters():
            for vs in p.verses(ch):
                if vs!='front': p.checks_for_verse(ch,vs)
        elapsed2=time.perf_counter()-t2
        self.assertLess(elapsed2,max(1.0,elapsed+0.1))

@unittest.skipUnless(ROOT.exists(),'real backend unavailable')
class ResponsiveUITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.app=BridgeApp(settings_path=Path(self.tmp.name)/'settings.json'); self.app.load_root(ROOT); self.app.update()
    def tearDown(self):
        try:self.app.destroy()
        except Exception:pass
        self.tmp.cleanup()

    def test_small_window_keeps_progress_tokens_cost_and_toolbar(self):
        self.app.geometry('760x560'); self.app.update(); time.sleep(.05); self.app.update()
        self.assertEqual(self.app.status_bar.winfo_manager(),'pack'); self.assertTrue(self.app.status_bar.winfo_ismapped()); self.assertEqual(self.app.job_progress.winfo_manager(),'grid')
        self.assertTrue(self.app.usage_var.get().startswith('Tokens')); self.assertTrue(self.app.cost_var.get().startswith('Cost'))
        self.assertEqual(self.app.notebook.tab(0,'text'),'Dash'); self.assertEqual(self.app.notebook.tab(2,'text'),'AI Review')
        self.assertEqual(self.app.align_toolbar.winfo_manager(),'grid'); self.assertFalse(bool(self.app.sidebar.winfo_manager()))
        self.assertTrue(all(w.winfo_ismapped() for w in self.app.dashboard_action_widgets))
        self.assertNotIn(str(self.app.align_group_frame),list(self.app.align_token_pane.panes()))
        self.app.notebook.select(self.app.align_tab); self.app.update()
        self.assertTrue(self.app.align_compact_group_frame.winfo_ismapped())
        self.assertEqual(self.app.compact_group_list.size(),self.app.group_list.size())


    def test_alignment_and_evidence_views_have_horizontal_scrolling(self):
        self.app.notebook.select(self.app.align_tab); self.app.geometry('760x560'); self.app.update()
        self.assertEqual(str(self.app.ai_preview.cget('wrap')),'none')
        self.assertTrue(str(self.app.ai_preview.cget('xscrollcommand')))
        self.assertTrue(str(self.app.top_list.cget('xscrollcommand')))
        self.assertTrue(str(self.app.bottom_list.cget('xscrollcommand')))
        self.assertTrue(str(self.app.group_list.cget('xscrollcommand')))
        self.assertTrue(str(self.app.compact_group_list.cget('xscrollcommand')))
        self.app.notebook.select(self.app.review_tab); self.app.update()
        self.assertEqual(str(self.app.review_detail.cget('wrap')),'none')
        self.assertTrue(str(self.app.review_detail.cget('xscrollcommand')))
        self.assertTrue(str(self.app.review_tree.cget('xscrollcommand')))

    def test_core_controls_have_tooltips(self):
        self.assertGreaterEqual(len(self.app._tooltips),20)
        self.assertTrue(self.app.api_test_btn.bind('<Enter>'))
        self.assertTrue(self.app.align_toolbar_widgets[0].bind('<Enter>'))

    def test_divider_never_owns_or_hides_alignment_toolbar(self):
        self.app.notebook.select(self.app.align_tab); self.app.update()
        self.assertNotEqual(self.app.align_toolbar.master,self.app.align_vertical_pane)
        self.assertTrue(self.app.align_toolbar.winfo_ismapped())
        self.assertEqual(str(self.app.align_vertical_pane.cget('orient')),'vertical')

    def test_final_review_panes_align_and_reflow(self):
        self.app.notebook.select(self.app.review_tab); self.app.geometry('1440x900'); self.app.update(); self.assertEqual(str(self.app.review_split.cget('orient')),'horizontal')
        self.app.geometry('900x650'); self.app.update(); time.sleep(.05); self.app.update(); self.assertTrue(self.app.review_left_frame.winfo_ismapped()); self.assertTrue(self.app.review_right_frame.winfo_ismapped())
        self.assertEqual(self.app.review_actions.winfo_manager(),'grid')


    def test_ai_proposal_sash_extremes_do_not_hide_action_buttons(self):
        self.app.notebook.select(self.app.align_tab); self.app.geometry('1000x700'); self.app.update()
        self.app.align_vertical_pane.sashpos(0, max(80,self.app.align_vertical_pane.winfo_height()-40)); self.app.update()
        self.assertTrue(self.app.align_toolbar.winfo_ismapped()); self.assertTrue(all(w.winfo_ismapped() for w in self.app.align_toolbar_widgets))
        self.app.align_vertical_pane.sashpos(0,80); self.app.update(); self.assertTrue(self.app.align_toolbar.winfo_ismapped())

    def test_destroy_handles_pending_after_callbacks(self):
        self.app.after(10000, lambda: None)
        self.app.after(12000, lambda: None)
        self.app.destroy()

    def test_internal_screenshot_style_product_title_removed_and_icon_loaded(self):
        texts=[]
        def walk(w):
            for c in w.winfo_children():
                try:
                    txt=c.cget('text')
                    if txt:texts.append(str(txt))
                except Exception:pass
                walk(c)
        walk(self.app)
        self.assertFalse(any(x.startswith('translationCore AI Bridge v0.') for x in texts),texts[:10])
        self.assertTrue(hasattr(self.app,'_app_icon_image'))

if __name__=='__main__': unittest.main(verbosity=2)
