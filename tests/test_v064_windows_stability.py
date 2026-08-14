from __future__ import annotations

import unittest
from pathlib import Path

from tc_ai_bridge.alignment_engine import AlignmentError, validate_preparation_proposal
from tc_ai_bridge.models import AlignmentGroup, TokenRef, VerseAlignment

ROOT = Path(__file__).resolve().parent.parent


class V064ProductionStabilityTests(unittest.TestCase):
    def test_automatic_preparation_cannot_remap_existing_human_alignment(self):
        h1=TokenRef('H1',1,1,type='topWord'); h2=TokenRef('H2',1,1,type='topWord')
        t1=TokenRef('T1',1,1,type='bottomWord'); t2=TokenRef('T2',1,1,type='bottomWord')
        verse=VerseAlignment([AlignmentGroup([h1],[t1]),AlignmentGroup([h2],[])],[t2])
        # H001/T001 is the established project relationship. Remapping T001 to H002
        # must be rejected in automatic Full Verse Review preparation.
        bad={'groups':[{'top_ids':['H001'],'bottom_ids':['T002'],'confidence':.9,'reason':'bad'},
                       {'top_ids':['H002'],'bottom_ids':['T001'],'confidence':.9,'reason':'bad'}],
             'review_notes':[]}
        with self.assertRaises(AlignmentError):
            validate_preparation_proposal(verse,bad)
        good={'groups':[{'top_ids':['H001'],'bottom_ids':['T001'],'confidence':.9,'reason':'preserve'},
                        {'top_ids':['H002'],'bottom_ids':['T002'],'confidence':.9,'reason':'fill'}],
              'review_notes':[]}
        self.assertEqual(len(validate_preparation_proposal(verse,good)),2)

    def test_windows_certification_runner_isolates_real_tk_tests(self):
        text=(ROOT/'tests'/'run_windows_certification.py').read_text('utf-8')
        batch=(ROOT/'test_windows.bat').read_text('utf-8')
        self.assertIn('ISOLATED TK GUI TESTS',text)
        self.assertIn("subprocess.run",text)
        self.assertIn('run_windows_certification.py',batch)
        self.assertNotIn('-m unittest discover -v',batch)

    def test_ui_shutdown_releases_nested_tk_wrappers_and_worker_queue_does_not_capture_root(self):
        text=(ROOT/'tc_ai_bridge'/'ui.py').read_text('utf-8')
        self.assertIn('def _release_tk_python_refs',text)
        self.assertIn('isinstance(value, tk.Image)',text)
        self.assertIn('ui_queue=self._ui_queue',text)
        # Inside the worker block, completion is queued through the captured queue rather
        # than by dereferencing self from the worker thread.
        block=text.split('def worker():',1)[1].split('thread=threading.Thread',1)[0]
        self.assertIn("ui_queue.put(('done',result))",block)
        self.assertNotIn('self._ui_queue.put',block)


if __name__=='__main__':
    unittest.main(verbosity=2)
