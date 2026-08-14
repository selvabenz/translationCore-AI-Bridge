from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from tc_ai_bridge.models import AlignmentGroup, QAIssue, TokenRef, VerseAlignment
from tc_ai_bridge.plugins import PluginRegistry
from tc_ai_bridge.review_policy import gate_ai_issues
from tc_ai_bridge.paratext_notes import validate_notes_11
from tc_ai_bridge.tc_project import TranslationCoreProject, TranslationCoreRoot

ROOT=Path(os.getenv('TC_TEST_ROOT','__missing_real_backend_fixture__'))


class V070CoreTests(unittest.TestCase):
    def test_false_positive_gate_suppresses_low_confidence_and_deduplicates(self):
        issues=[
            QAIssue('AI_MEANING','critical','Possible meaning issue','Maybe wrong',source='OpenAI',confidence=.41),
            QAIssue('AI_STYLE','medium','Possible style issue','Maybe awkward',source='OpenAI',confidence=.31),
            QAIssue('AI_TERM','high','Terminology mismatch','Evidence: TW article supports review',source='OpenAI',check_id='c1',confidence=.91),
            QAIssue('AI_TERM','high','Terminology mismatch','Evidence: duplicate',source='OpenAI',check_id='c1',confidence=.70),
        ]
        active,suppressed=gate_ai_issues(issues)
        self.assertEqual(len(suppressed),1)
        self.assertEqual(suppressed[0].code,'AI_STYLE')
        self.assertEqual(len(active),2)
        retained=next(x for x in active if x.code=='AI_MEANING')
        self.assertEqual(retained.severity,'medium')
        term=next(x for x in active if x.code=='AI_TERM')
        self.assertEqual(term.severity,'high')
        self.assertGreaterEqual(term.confidence,.9)

    def test_language_registry_detects_target_plugins_and_source_scripts(self):
        r=PluginRegistry()
        fake=SimpleNamespace(manifest={'target_language':{'id':'hi','name':'Hindi'}},book_id='mat',summary=None)
        a=VerseAlignment([AlignmentGroup([TokenRef('λόγος')],[TokenRef('वचन',type='bottomWord')])],[])
        ctx=r.detect_project(fake,a,'वचन')
        self.assertEqual(ctx.target_id,'hi')
        self.assertEqual(ctx.target_name,'Hindi')
        self.assertEqual(ctx.source_id,'el-x-koine')
        self.assertNotIn('sandhi',ctx.qa_categories)
        fake2=SimpleNamespace(manifest={'target_language':{'id':'ta','name':'தமிழ்'}},book_id='psa',summary=None)
        b=VerseAlignment([AlignmentGroup([TokenRef('דָּבָר')],[TokenRef('வார்த்தை',type='bottomWord')])],[])
        ctx2=r.detect_project(fake2,b,'வார்த்தை')
        self.assertEqual(ctx2.source_id,'hbo'); self.assertEqual(ctx2.target_id,'ta'); self.assertIn('sandhi',ctx2.qa_categories)

    @unittest.skipUnless(ROOT.exists(),'real backend unavailable')
    def test_real_tamil_project_is_manifest_detected(self):
        projects={p.book_id:p for p in TranslationCoreRoot(ROOT).projects()}
        p=projects.get('rut') or next(iter(projects.values()))
        ch=next(iter(p.chapters())); vs=next(v for v in p.verses(ch) if v!='front')
        a=p.load_verse_alignment(ch,vs)
        ctx=PluginRegistry().detect_project(p,a,p.target_verse_text(ch,vs))
        if str((p.manifest.get('target_language') or {}).get('id','')).lower()=='ta':
            self.assertEqual(ctx.target_id,'ta')

    @unittest.skipUnless(ROOT.exists(),'real backend unavailable')
    def test_paratext_notes_11_comment_does_not_modify_scripture(self):
        projects={p.book_id:p for p in TranslationCoreRoot(ROOT).projects()}
        src=projects.get('rut') or next(iter(projects.values()))
        with tempfile.TemporaryDirectory() as td:
            dst=Path(td)/src.path.name
            shutil.copytree(src.path,dst)
            p=TranslationCoreProject(dst)
            ch=next(iter(p.chapters())); vs=next(v for v in p.verses(ch) if v!='front')
            chapter_file=p.book_dir/f'{ch}.json'; before=chapter_file.read_bytes() if chapter_file.exists() else b''
            out=p.record_paratext_note(ch,vs,'Reviewer requests consultant discussion.',username='Reviewer A',selected_text='',note_type='AI Bridge QA Discussion',metadata={'decision':'needs_discussion','severity':'high'})
            info=validate_notes_11(out)
            self.assertEqual(info['version'],'1.1'); self.assertEqual(info['threads'],1)
            root=ET.parse(out).getroot(); thread=root.find('thread'); self.assertIsNotNone(thread)
            self.assertEqual(thread.find('selection').attrib['verseRef'],f'{p.book_id.upper()} {ch}:{vs}')
            self.assertEqual(thread.find('comment').attrib['user'],'Reviewer A')
            self.assertIn('Reviewer requests',thread.find('comment').find('content').text)
            if chapter_file.exists(): self.assertEqual(before,chapter_file.read_bytes())

    def test_new_official_logo_is_packaged(self):
        root=Path(__file__).resolve().parents[1]
        self.assertTrue((root/'assets'/'app_icon.ico').is_file())
        self.assertGreater((root/'assets'/'app_icon.png').stat().st_size,10000)


class ResponsiveUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ROOT.exists(): raise unittest.SkipTest('real backend unavailable')

    def setUp(self):
        from tc_ai_bridge.ui import BridgeApp
        self.tmp=tempfile.TemporaryDirectory()
        self.app=BridgeApp(settings_path=Path(self.tmp.name)/'settings.json')
        self.app.withdraw(); self.app.load_root(str(ROOT)); self.app.update_idletasks(); self.app.update()

    def tearDown(self):
        try:self.app.destroy()
        except Exception:pass
        self.tmp.cleanup()

    def test_language_labels_shortcuts_and_overflow_controls_exist(self):
        app=self.app
        self.assertIsNotNone(app.language_context)
        self.assertIn(app.language_context.target_name,app.align_bottom_frame.cget('text'))
        self.assertIn(app.language_context.source_name,app.align_top_frame.cget('text'))
        # Review speed controls
        self.assertTrue(app.bind_all('<F8>'))
        self.assertTrue(app.bind_all('<Control-Return>'))
        # Major long-form viewers expose horizontal scrolling callbacks.
        for w in (app.ai_preview,app.review_detail,app.qa_detail,app.tc_detail,app.kb_detail,app.term_detail,app.psalms_detail,app.log_text):
            self.assertTrue(str(w.cget('xscrollcommand')))

    def test_ai_proposal_language_and_confidence_color_tags(self):
        app=self.app
        current=app.session.current
        from tc_ai_bridge.alignment_engine import make_inventory
        inv=make_inventory(current)
        top=next(iter(inv.top_ids)); bottom=next(iter(inv.bottom_ids))
        proposal={'groups':[{'top_ids':[top],'bottom_ids':[bottom],'confidence':.91,'reason':'Meaning corresponds in context.'}],'review_notes':['Review if terminology differs.']}
        app._render_ai_proposal(current,proposal)
        text=app.ai_preview.get('1.0','end')
        self.assertIn(app.language_context.source_name,text)
        self.assertIn(app.language_context.target_name,text)
        self.assertIn('English rationale',text)
        tags=set(app.ai_preview.tag_names())
        self.assertTrue({'source_lang','target_lang','english','conf_high','conf_mid','conf_low'}.issubset(tags))
        self.assertIn('91%',text)

    def test_small_screen_toolbars_reflow_without_losing_review_actions(self):
        app=self.app; app.deiconify(); app.geometry('760x560'); app.update_idletasks(); app.update(); app._on_responsive_resize(); app.update_idletasks()
        self.assertTrue(all(w.winfo_manager() for w in app.review_action_widgets))
        self.assertTrue(all(w.winfo_manager() for w in app.qa_toolbar_widgets))
        app.notebook.select(app.align_tab); app.update_idletasks(); self.assertTrue(app.align_compact_group_frame.winfo_manager())


if __name__=='__main__': unittest.main()
