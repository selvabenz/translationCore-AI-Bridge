from __future__ import annotations

import copy
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from tc_ai_bridge.alignment_engine import apply_proposal, validate_proposal
from tc_ai_bridge.alignment_reliability import (
    compile_link_proposal, make_request_context, request_context_matches,
    proposal_difference, structural_issues,
)
from tc_ai_bridge.identity import detect_project_identity
from tc_ai_bridge.models import AlignmentGroup, TokenRef, VerseAlignment
from tc_ai_bridge.paratext_connector import ParatextConnectorClient, ParatextConnectorError
from tc_ai_bridge.tc_project import TranslationCoreRoot

REAL_ROOT = Path(os.getenv('TC_TEST_ROOT', '__missing_real_backend_fixture__'))


def H(word: str, occ: int = 1, occs: int = 1) -> TokenRef:
    return TokenRef(word, occ, occs, lemma=word)


def T(word: str, occ: int = 1, occs: int = 1) -> TokenRef:
    return TokenRef(word, occ, occs, type='bottomWord')


class CompilerEdgeCaseTests(unittest.TestCase):
    def test_many_to_one_duplicate_ai_links_compile_to_one_group(self):
        v=VerseAlignment([AlignmentGroup([H('א')],[]),AlignmentGroup([H('ב')],[])],[T('தமிழ்')])
        raw={'links':[{'top_id':'H001','bottom_id':'T001','confidence':.94,'reason':'a'},
                      {'top_id':'H002','bottom_id':'T001','confidence':.89,'reason':'b'}],
             'implicit_top_ids':[],'review_notes':[]}
        p=compile_link_proposal(v,raw)
        validate_proposal(v,p)
        groups=[g for g in p['groups'] if g['bottom_ids']]
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0]['top_ids'],['H001','H002'])
        self.assertEqual(groups[0]['bottom_ids'],['T001'])
        self.assertEqual(groups[0]['relation'],'many-to-one')
        self.assertAlmostEqual(groups[0]['confidence'],.89)

    def test_one_to_many_and_many_to_many_compile_deterministically(self):
        v=VerseAlignment([AlignmentGroup([H('א')],[]),AlignmentGroup([H('ב')],[])],[T('ஒன்று'),T('இரண்டு')])
        raw={'links':[{'top_id':'H001','bottom_id':'T001','confidence':.95,'reason':'x'},
                      {'top_id':'H001','bottom_id':'T002','confidence':.92,'reason':'x'},
                      {'top_id':'H002','bottom_id':'T001','confidence':.91,'reason':'y'}],
             'implicit_top_ids':[],'review_notes':[]}
        p1=compile_link_proposal(v,raw); p2=compile_link_proposal(v,copy.deepcopy(raw))
        self.assertEqual(p1['groups'],p2['groups'])
        g=next(g for g in p1['groups'] if g['bottom_ids'])
        self.assertEqual(g['relation'],'many-to-many')
        self.assertEqual(set(g['top_ids']),{'H001','H002'})
        self.assertEqual(set(g['bottom_ids']),{'T001','T002'})

    def test_weak_bridge_does_not_overmerge_components(self):
        v=VerseAlignment([AlignmentGroup([H('א')],[]),AlignmentGroup([H('ב')],[])],[T('ஒன்று'),T('இரண்டு')])
        raw={'links':[{'top_id':'H001','bottom_id':'T001','confidence':.96,'reason':'strong'},
                      {'top_id':'H002','bottom_id':'T002','confidence':.95,'reason':'strong'},
                      {'top_id':'H001','bottom_id':'T002','confidence':.50,'reason':'speculative bridge'}],
             'implicit_top_ids':[],'review_notes':[]}
        p=compile_link_proposal(v,raw)
        nonempty=[g for g in p['groups'] if g['bottom_ids']]
        self.assertEqual(len(nonempty),2)
        self.assertEqual(len(p['uncertain_links']),1)
        self.assertTrue(p['requires_human_review'])

    def test_protected_legacy_group_can_be_extended_only_as_explicit_proposal(self):
        h1,h2=H('א'),H('ב'); t1,t2=T('ஒன்று'),T('இரண்டு')
        v=VerseAlignment([AlignmentGroup([h1],[t1]),AlignmentGroup([h2],[])],[t2])
        raw={'links':[{'top_id':'H001','bottom_id':'T002','confidence':.90,'reason':'target gap belongs with existing source'}],
             'implicit_top_ids':[],'review_notes':[]}
        p=compile_link_proposal(v,raw,lock_policy='protected')
        g=next(g for g in p['groups'] if 'T002' in g['bottom_ids'])
        self.assertEqual(g['origin'],'extended_protected')
        self.assertEqual(set(g['bottom_ids']),{'T001','T002'})
        # Project object is untouched until human explicitly applies the proposal.
        self.assertEqual(v.alignments[0].bottom_words,[t1])

    def test_hard_lock_blocks_extension(self):
        h1,h2=H('א'),H('ב'); t1,t2=T('ஒன்று'),T('இரண்டு')
        v=VerseAlignment([AlignmentGroup([h1],[t1]),AlignmentGroup([h2],[])],[t2])
        raw={'links':[{'top_id':'H001','bottom_id':'T002','confidence':.97,'reason':'try extension'}],
             'implicit_top_ids':[],'review_notes':[]}
        p=compile_link_proposal(v,raw,lock_policy='hard')
        self.assertTrue(p['conflicts'])
        self.assertEqual(next(g for g in p['groups'] if 'H001' in g['top_ids'])['bottom_ids'],['T001'])

    def test_bridge_between_two_protected_groups_is_rejected(self):
        h1,h2,h3=H('א'),H('ב'),H('ג'); t1,t2,t3=T('ஒன்று'),T('இரண்டு'),T('மூன்று')
        v=VerseAlignment([AlignmentGroup([h1],[t1]),AlignmentGroup([h2],[t2]),AlignmentGroup([h3],[])],[t3])
        raw={'links':[{'top_id':'H001','bottom_id':'T003','confidence':.9,'reason':'A'},
                      {'top_id':'H003','bottom_id':'T003','confidence':.9,'reason':'bridge'},
                      {'top_id':'H003','bottom_id':'T002','confidence':.9,'reason':'B'}],
             'implicit_top_ids':[],'review_notes':[]}
        p=compile_link_proposal(v,raw)
        self.assertTrue(any(x['type']=='protected_component_bridge' for x in p['conflicts']))
        # Both protected groups are still represented exactly.
        self.assertTrue(any(g['top_ids']==['H001'] and g['bottom_ids']==['T001'] for g in p['groups']))
        self.assertTrue(any(g['top_ids']==['H002'] and g['bottom_ids']==['T002'] for g in p['groups']))

    def test_implicit_source_is_preserved_without_forced_target(self):
        v=VerseAlignment([AlignmentGroup([H('א')],[])],[T('தமிழ்')])
        raw={'links':[],'implicit_top_ids':['H001'],'review_notes':[]}
        p=compile_link_proposal(v,raw)
        g=p['groups'][0]
        self.assertEqual(g['bottom_ids'],[]); self.assertEqual(g['origin'],'implicit')
        applied=apply_proposal(v,p)
        self.assertEqual(len(applied.word_bank),1)

    def test_fifty_equivalent_link_orders_compile_identically(self):
        import random
        v=VerseAlignment([AlignmentGroup([H('א')],[]),AlignmentGroup([H('ב')],[])],[T('ஒன்று'),T('இரண்டு')])
        base=[{'top_id':'H001','bottom_id':'T001','confidence':.93,'reason':'a'},
              {'top_id':'H002','bottom_id':'T001','confidence':.88,'reason':'b'},
              {'top_id':'H002','bottom_id':'T002','confidence':.86,'reason':'c'}]
        expected=None
        rng=random.Random(73)
        for _ in range(50):
            links=copy.deepcopy(base); rng.shuffle(links)
            p=compile_link_proposal(v,{'links':links,'implicit_top_ids':[],'review_notes':[]})
            shape=[(tuple(g['top_ids']),tuple(g['bottom_ids'])) for g in p['groups']]
            if expected is None: expected=shape
            self.assertEqual(shape,expected)

    def test_duplicate_identical_link_is_deduplicated_before_grouping(self):
        v=VerseAlignment([AlignmentGroup([H('א')],[])],[T('ஒன்று')])
        link={'top_id':'H001','bottom_id':'T001','confidence':.93,'reason':'same'}
        p=compile_link_proposal(v,{'links':[link,copy.deepcopy(link)],'implicit_top_ids':[],'review_notes':[]})
        self.assertEqual(len(p['links']),1)
        self.assertTrue(any(d.get('type')=='duplicate_link' for d in p['diagnostics']))
        validate_proposal(v,p)

    def test_target_only_candidate_stays_in_wordbank_and_requires_human_review(self):
        v=VerseAlignment([AlignmentGroup([H('א')],[])],[T('இயல்பான')])
        p=compile_link_proposal(v,{'links':[],'implicit_top_ids':[],'target_only_ids':['T001'],'review_notes':[]})
        self.assertEqual(p['target_only_ids'],['T001'])
        self.assertTrue(p['requires_human_review'])
        applied=apply_proposal(v,p)
        self.assertEqual([x.word for x in applied.word_bank],['இயல்பான'])

    def test_discontinuous_token_ids_can_form_one_phrase_group(self):
        v=VerseAlignment([AlignmentGroup([H('א')],[]),AlignmentGroup([H('ב')],[]),AlignmentGroup([H('ג')],[])],[T('ஒன்று'),T('இரண்டு'),T('மூன்று')])
        raw={'links':[{'top_id':'H001','bottom_id':'T001','confidence':.9,'reason':'phrase'},
                      {'top_id':'H003','bottom_id':'T001','confidence':.9,'reason':'phrase'},
                      {'top_id':'H003','bottom_id':'T003','confidence':.9,'reason':'phrase'}],
             'implicit_top_ids':[],'review_notes':[]}
        p=compile_link_proposal(v,raw)
        g=next(g for g in p['groups'] if 'H001' in g['top_ids'])
        self.assertEqual(g['top_ids'],['H001','H003'])
        self.assertEqual(g['bottom_ids'],['T001','T003'])
        self.assertEqual(g['relation'],'many-to-many')
        validate_proposal(v,p)

    def test_unknown_ai_token_id_is_rejected_before_compilation(self):
        v=VerseAlignment([AlignmentGroup([H('א')],[])],[T('ஒன்று')])
        with self.assertRaises(Exception):
            compile_link_proposal(v,{'links':[{'top_id':'H999','bottom_id':'T001','confidence':.9,'reason':'bad'}],'implicit_top_ids':[],'review_notes':[]})

    def test_structural_diagnostics_detect_duplicate_historical_membership(self):
        t=T('x')
        v=VerseAlignment([AlignmentGroup([H('a')],[t]),AlignmentGroup([H('b')],[t])],[])
        issues=structural_issues(v)
        self.assertTrue(any('target token' in x for x in issues))


class RequestContextTests(unittest.TestCase):
    class P:
        def __init__(self): self.path=Path('/tmp/project'); self.book_id='rut'; self.text='abc'
        def target_verse_text(self,ch,vs): return self.text

    def test_navigation_or_text_change_invalidates_ai_result(self):
        p=self.P(); v=VerseAlignment([AlignmentGroup([H('a')],[])],[T('x')])
        c=make_request_context(p,'1','1',v)
        self.assertTrue(request_context_matches(c,p,'1','1',v))
        self.assertFalse(request_context_matches(c,p,'1','2',v))
        p.text='changed'
        self.assertFalse(request_context_matches(c,p,'1','1',v))

    def test_alignment_mutation_invalidates_ai_result_even_on_same_verse(self):
        p=self.P(); v=VerseAlignment([AlignmentGroup([H('a')],[])],[T('x')])
        c=make_request_context(p,'1','1',v)
        mutated=VerseAlignment([AlignmentGroup([H('a')],[T('x')])],[])
        self.assertFalse(request_context_matches(c,p,'1','1',mutated))
        self.assertNotEqual(c.request_id,make_request_context(p,'1','1',v).request_id)


class IdentityTests(unittest.TestCase):
    def test_door43_username_from_project_git_email(self):
        with tempfile.TemporaryDirectory() as td:
            cfg=Path(td)/'.git'/'config'; cfg.parent.mkdir()
            cfg.write_text('[user]\n\tname = Benz\n\temail = 52540+benz@noreply.door43.org\n',encoding='utf-8')
            d=detect_project_identity(td)
            self.assertEqual(d['door43_username'],'benz')
            self.assertEqual(d['git_name'],'Benz')
            self.assertNotIn('password',str(d).lower())


class ConnectorFoundationTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'non-Windows behavior only')
    def test_local_paratext_connector_fails_closed_off_windows(self):
        with self.assertRaises(ParatextConnectorError): ParatextConnectorClient().get_state()


@unittest.skipUnless(REAL_ROOT.exists(), 'real uploaded translationCore backend not present')
class ExistingWorkCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=TranslationCoreRoot(REAL_ROOT)
        cls.project=next(iter(cls.root.projects()))

    def test_compatibility_scan_is_read_only(self):
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.project.alignment_dir.glob('*.json')}
        scan=self.project.alignment_compatibility_scan()
        after={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.project.alignment_dir.glob('*.json')}
        self.assertEqual(before,after)
        self.assertEqual(scan['filesModified'],0)
        self.assertEqual(scan['verses'],sum(1 for ch in self.project.chapters() for vs in self.project.verses(ch) if vs!='front'))

    def test_existing_completed_work_is_not_reprocessed_by_snapshot(self):
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.project.alignment_dir.glob('*.json')}
        snap=self.project.ensure_v073_migration_snapshot(); self.assertTrue(snap.exists())
        after={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.project.alignment_dir.glob('*.json')}
        self.assertEqual(before,after)

    def test_real_project_door43_git_identity_when_available(self):
        candidates=[p for p in self.root.projects() if (p.path/'.git'/'config').exists()]
        if not candidates:self.skipTest('fixture has no project git config')
        d=detect_project_identity(candidates[0].path)
        self.assertTrue(d['git_name'] or d['door43_username'])


class ResponsiveUITests(unittest.TestCase):
    """v0.7.4 UI tests are isolated by the Windows certification runner."""
    def setUp(self):
        from tc_ai_bridge.ui import BridgeApp
        self.tmp=tempfile.TemporaryDirectory()
        self.app=BridgeApp(settings_path=Path(self.tmp.name)/'settings.json')
        self.app.withdraw(); self.app.update_idletasks()

    def tearDown(self):
        try:self.app.destroy()
        except Exception:pass
        self.tmp.cleanup()

    def _all_text(self, widget):
        out=[]
        for child in widget.winfo_children():
            try:
                text=str(child.cget('text'))
                if text:out.append(text)
            except Exception:pass
            out.extend(self._all_text(child))
        return out

    def test_alignment_toolbar_exposes_reliability_workflow(self):
        labels=[str(w.cget('text')) for w in self.app.align_toolbar_widgets]
        self.assertIn('Fill Alignment Gaps',labels)
        self.assertIn('Audit Existing Alignment',labels)
        self.assertIn('More…',labels)
        menu_labels=[self.app.align_toolbar_widgets[-1]._menu_ref.entrycget(i,'label') for i in range(self.app.align_toolbar_widgets[-1]._menu_ref.index('end')+1) if self.app.align_toolbar_widgets[-1]._menu_ref.type(i)!='separator']
        self.assertIn('Alignment Diagnostics…',menu_labels)
        self.assertNotIn('AI Suggest Alignment',labels)
        self.assertNotIn('AI Suggest',labels)

    def test_production_tab_exposes_existing_work_scan_and_local_connector(self):
        labels='\n'.join(self._all_text(self.app.production_tab))
        self.assertIn('Existing Work Scan',labels)
        self.assertIn('Paratext · Live Connector + Project Notes',labels)
        self.assertIn('Connect / Refresh',labels)
        self.assertIn('Sync verse navigation',labels)
        self.assertFalse(self.app.paratext_nav_sync_var.get())

    def test_alignment_reliability_controls_have_human_safety_tooltips(self):
        tips='\n'.join(t.text for t in self.app._tooltips)
        self.assertIn('unresolved relationships',tips)
        self.assertIn('existing project alignment stays protected',tips)
        self.assertIn('Read-only whole-verse AI audit',tips)
        self.assertIn('compiler normalization',tips)


if __name__=='__main__': unittest.main(verbosity=2)
