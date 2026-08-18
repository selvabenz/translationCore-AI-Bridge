from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from tc_ai_bridge.paratext_api import ParatextDataAccessClient
from tc_ai_bridge.paratext_notes import append_paratext_note, validate_notes_11
from tc_ai_bridge.secret_store import AppSettings
from tc_ai_bridge.text_graphemes import indic_grapheme_boundaries, nearest_grapheme_boundary


class V072CoreTests(unittest.TestCase):
    def test_tamil_grapheme_boundaries_keep_marks_and_pulli_clusters_together(self):
        # கொ = KA + vowel sign; க்க = KA + pulli/virama + KA.
        self.assertEqual(indic_grapheme_boundaries('கொ'),[0,2])
        self.assertEqual(indic_grapheme_boundaries('க்க'),[0,3])
        self.assertEqual(nearest_grapheme_boundary('கொ',1),2)
        self.assertNotIn(1,indic_grapheme_boundaries('பூமியின்மேல்'))

    def test_official_notes11_attaches_to_exact_selected_target_text(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'Notes_AI_Suggestion.xml'
            verse='உங்களுக்கும் அதற்கும் 3,000 அடிகள் தூரம் இடைவெளி இருக்கவேண்டும்.'
            out,_=append_paratext_note(
                p,book_id='JOS',chapter=3,verse=4,verse_text=verse,
                comment_text='ஒரு கிலோமீட்டர்',reviewer='Yesu Selva Benz',selected_text='3,000 அடிகள்',ext_user='AI Suggestion')
            info=validate_notes_11(out); self.assertEqual(info['threads'],1)
            root=ET.parse(out).getroot(); thread=root.find('thread'); sel=thread.find('selection'); comment=thread.find('comment')
            snapshot='\\v 4 '+verse
            self.assertEqual(sel.attrib['verseRef'],'JOS 3:4')
            self.assertEqual(sel.attrib['selectedText'],'3,000 அடிகள்')
            self.assertEqual(int(sel.attrib['startPos']),snapshot.find('3,000 அடிகள்'))
            self.assertTrue(sel.attrib['beforeContext'].endswith('அதற்கும் '))
            self.assertTrue(sel.attrib['afterContext'].startswith(' தூரம்'))
            self.assertEqual(comment.attrib['user'],'Yesu Selva Benz')
            self.assertEqual(comment.attrib['extUser'],'AI Suggestion')

    def test_discontinuous_or_spacing_selection_reattaches_to_longest_exact_segment(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'Notes_AI_Suggestion.xml'
            # The reconstructed selection contains a token that does not occur contiguously.
            out,_=append_paratext_note(p,book_id='RUT',chapter=2,verse=8,verse_text='மகளே, கேள்; இங்கே இரு.',comment_text='Review',reviewer='Member',selected_text='மகளே கேள் இங்கே')
            sel=ET.parse(out).getroot().find('thread').find('selection')
            self.assertIn(sel.attrib['selectedText'],('கேள்','இங்கே'))
            self.assertGreaterEqual(int(sel.attrib['startPos']),0)

    def test_paratext_registration_code_can_be_session_only(self):
        with tempfile.TemporaryDirectory() as td:
            s=AppSettings(Path(td)/'settings.json')
            s.paratext_username='Member'; s.paratext_project_guid='abc123'; s.set_paratext_registration_code('secret-code',persist=False)
            self.assertEqual(s.get_paratext_registration_code(),'secret-code')
            saved=json.loads((Path(td)/'settings.json').read_text('utf-8'))
            self.assertNotIn('secret-code',json.dumps(saved))

    def test_paratext_guid_mapping_is_per_translationcore_project(self):
        with tempfile.TemporaryDirectory() as td:
            s=AppSettings(Path(td)/'settings.json')
            s.set_paratext_project_guid('project-ruth','guid-ruth')
            s.set_paratext_project_guid('project-psalms','guid-psalms')
            self.assertEqual(s.get_paratext_project_guid('project-ruth'),'guid-ruth')
            self.assertEqual(s.get_paratext_project_guid('project-psalms'),'guid-psalms')
            self.assertEqual(s.get_paratext_project_guid('project-genesis'),'')

    def test_paratext_project_membership_verification_uses_authenticated_projects(self):
        class FakeResponse:
            def __init__(self,data): self.data=data
            def __enter__(self): return self
            def __exit__(self,*a): return False
            def read(self): return self.data
        calls=[]
        def fake_urlopen(req,timeout=0):
            calls.append(req)
            if 'token' in req.full_url:
                return FakeResponse(b'{"access_token":"jwt-token"}')
            return FakeResponse(b'<repos><repo><proj>TAMIL</proj><projid>guid-ta</projid><projecttype>Standard</projecttype></repo></repos>')
        with patch.object(urllib.request,'urlopen',side_effect=fake_urlopen):
            c=ParatextDataAccessClient('Member','registration',registry_token_url='https://registry.example/api8/token/',data_access_base='https://data.example')
            project=c.verify_project_membership('guid-ta')
        self.assertEqual(project['short_name'],'TAMIL')
        self.assertEqual(project['guid'],'guid-ta')
        self.assertEqual(calls[-1].full_url,'https://data.example/api8/projects')
        self.assertEqual(calls[-1].headers.get('Authorization'),'Bearer jwt-token')

    def test_paratext_data_access_client_posts_notes_to_project_guid(self):
        class FakeResponse:
            def __init__(self,data): self.data=data
            def __enter__(self): return self
            def __exit__(self,*a): return False
            def read(self): return self.data
        calls=[]
        def fake_urlopen(req,timeout=0):
            calls.append(req)
            if 'token' in req.full_url:
                return FakeResponse(b'{"access_token":"jwt-token"}')
            return FakeResponse(b'new-tip-id')
        with tempfile.TemporaryDirectory() as td:
            notes=Path(td)/'Notes_AI_Suggestion.xml'
            append_paratext_note(notes,book_id='RUT',chapter=1,verse=1,verse_text='ஒரு வசனம்',comment_text='Review',reviewer='Member',selected_text='வசனம்')
            with patch.object(urllib.request,'urlopen',side_effect=fake_urlopen):
                c=ParatextDataAccessClient('Member','registration',registry_token_url='https://registry.example/api8/token/',data_access_base='https://data.example')
                result=c.post_notes('project-guid',notes)
        self.assertEqual(result,'new-tip-id'); self.assertEqual(len(calls),2)
        self.assertEqual(calls[1].full_url,'https://data.example/api8/notes/project-guid')
        self.assertEqual(calls[1].headers.get('Authorization'),'Bearer jwt-token')
        self.assertIn(b'<notes version="1.1">',calls[1].data)


class ResponsiveUITests(unittest.TestCase):
    def setUp(self):
        from tc_ai_bridge.ui import BridgeApp
        self.tmp=tempfile.TemporaryDirectory()
        self.app=BridgeApp(settings_path=Path(self.tmp.name)/'settings.json')
        self.app.withdraw(); self.app.update_idletasks()

    def tearDown(self):
        try:self.app.destroy()
        except Exception:pass
        self.tmp.cleanup()

    def test_dashboard_exception_summary_uses_wrapped_detail_not_horizontal_tree(self):
        app=self.app
        self.assertEqual(tuple(app.exception_tree.cget('columns')),('ref','cache','critical','high','medium','checks'))
        self.assertEqual(str(app.exception_detail.cget('wrap')),'word')
        self.assertFalse(str(app.exception_tree.cget('xscrollcommand')))
        self.assertEqual(str(app.review_detail.cget('wrap')),'word')
        self.assertFalse(str(app.review_detail.cget('xscrollcommand')))
        app._exception_rows=[{'chapter':'1','verse':'17','cache':'stale','counts':{'critical':1,'high':3,'medium':0},'checks':0,'summary':'A very long summary '+('தமிழ் English evidence ' * 30)}]
        app.exception_tree.insert('','end',iid='0',values=('1:17','STALE',1,3,0,0)); app.exception_tree.selection_set('0'); app._dashboard_exception_selected()
        self.assertIn('A very long summary',app.exception_detail.get('1.0','end'))
        self.assertGreater(len(app.exception_detail.get('1.0','end')),400)

    def test_shortcuts_are_tooltips_not_button_labels(self):
        app=self.app
        labels=[str(w.cget('text')) for w in app.review_header_widgets+app.review_action_widgets+app.qa_toolbar_widgets]
        self.assertFalse(any('F5' in x or 'F8' in x or 'Ctrl+' in x for x in labels),labels)
        tips='\n'.join(t.text for t in app._tooltips)
        for shortcut in ('F5','F8','Ctrl+Enter','Ctrl+Shift+D','Ctrl+Shift+R'):
            self.assertIn(shortcut,tips)

    def test_tamil_editor_caret_snaps_out_of_combining_cluster(self):
        import tkinter as tk
        w=tk.Text(self.app); w.insert('1.0','கொடுக்க'); self.app._configure_grapheme_safe_editor(w)
        w.mark_set('insert','1.1'); self.app._snap_text_insert_to_grapheme(w)
        self.assertNotEqual(w.index('insert'),'1.1')
        self.assertEqual(str(w.cget('insertwidth')),'1')
        w.destroy()

    def test_ai_green_lamp_blink_lifecycle(self):
        app=self.app
        app._busy=True; app._bg_is_ai=True; app._api_state='connected'; app._start_ai_blink(); app.update_idletasks()
        self.assertIsNotNone(app._ai_blink_after_id)
        self.assertTrue(app._ai_blink_phase)
        app._stop_ai_blink(redraw=True)
        self.assertIsNone(app._ai_blink_after_id)
        app._busy=False; app._bg_is_ai=False

    def test_paratext_settings_identify_external_ai_author(self):
        app=self.app
        self.assertEqual(app.paratext_guid_var.get(),'')
        self.assertEqual(app.paratext_username_var.get(),'')
        # The fixed author is visible in the settings subtree; inspect labels recursively.
        def labels(w):
            out=[]
            for c in w.winfo_children():
                try: out.append(str(c.cget('text')))
                except Exception: pass
                out.extend(labels(c))
            return out
        self.assertIn('AI Suggestion',' '.join(labels(app.settings_tab)))


if __name__=='__main__':
    unittest.main()
