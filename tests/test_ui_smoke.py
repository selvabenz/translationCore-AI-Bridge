from __future__ import annotations
import unittest
import os
import tempfile
from pathlib import Path
from tc_ai_bridge.ui import BridgeApp

ROOT=os.getenv('TC_TEST_ROOT','__missing_real_backend_fixture__')

class UISmoke(unittest.TestCase):
    @unittest.skipUnless(Path(ROOT).exists(),'real backend unavailable')
    def test_ui_loads_real_root_and_navigates(self):
        with tempfile.TemporaryDirectory() as td:
            app=BridgeApp(settings_path=Path(td)/'settings.json')
            try:
                app.withdraw()
                app.load_root(ROOT)
                self.assertGreaterEqual(len(app.projects),1)
                self.assertIsNotNone(app.session)
                self.assertGreater(app.top_list.size(),0)
                self.assertGreater(app.bottom_list.size(),0)
                self.assertIsNotNone(app.kb)
                self.assertGreater(len(app.kb_tree.get_children()),0)
                # Exercise real UI edit wiring without writing.
                app.top_list.selection_set(0); app.bottom_list.selection_set(0)
                app._connect_selected(); self.assertTrue(app.session.dirty)
                app._undo(); app._redo(); self.assertTrue(app.session.dirty)
                app._run_local_qa(); self.assertGreaterEqual(len(app._qa_items),1)
                app.session.mark_saved()
                app.update_idletasks()
            finally:
                try: app.destroy()
                except Exception: pass

if __name__=='__main__':unittest.main(verbosity=2)
