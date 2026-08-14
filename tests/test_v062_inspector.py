from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from inspect_companion_state import scan

class CompanionInspectorTests(unittest.TestCase):
    def test_inspector_is_read_only_and_detects_test_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); c=root/'projects'/'p'/'/.apps'  # placeholder to avoid accidental path typo
            c=root/'projects'/'p'/'.apps'/'translationCoreAI'/'aiReview'; c.mkdir(parents=True)
            f=c/'x.json'; f.write_text('{"summary":"Mock full review"}','utf-8'); before=f.read_bytes()
            rows=scan(root); self.assertEqual(len(rows),1); self.assertTrue(rows[0][4]); self.assertEqual(f.read_bytes(),before)

if __name__=='__main__': unittest.main(verbosity=2)
