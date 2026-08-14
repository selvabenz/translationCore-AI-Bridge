from __future__ import annotations
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class WindowsBootstrapPatchTests(unittest.TestCase):
    def test_ui_has_no_pillow_dependency(self):
        src=(ROOT/'tc_ai_bridge'/'ui.py').read_text('utf-8')
        self.assertNotIn('from PIL',src)
        self.assertNotIn('import PIL',src)
        self.assertIn("tk.PhotoImage(file=str(p))",src)

    def test_runtime_requirements_do_not_require_pillow(self):
        req=(ROOT/'requirements.txt').read_text('utf-8').lower()
        self.assertNotIn('pillow',req)
        self.assertNotIn('pil=',req)

    def test_windows_bootstrap_is_isolated_and_test_runner_accepts_backend(self):
        setup=(ROOT/'setup_windows.bat').read_text('utf-8').lower()
        test=(ROOT/'test_windows.bat').read_text('utf-8').lower()
        self.assertIn('set "pythonhome="',setup)
        self.assertIn('set "pythonpath="',setup)
        self.assertIn('-m venv .venv',setup)
        self.assertIn('tc_test_root',test)
        self.assertIn('portable tests passed',test)
        self.assertTrue((ROOT/'certify_windows.bat').exists())
        self.assertTrue((ROOT/'diagnose_windows.bat').exists())

    def test_patch_version_is_consistent_in_runtime_and_installer(self):
        version=(ROOT/'VERSION').read_text('utf-8').strip()
        init=(ROOT/'tc_ai_bridge'/'__init__.py').read_text('utf-8')
        installer=(ROOT/'installer'/'translationCore-AI-Bridge.iss').read_text('utf-8')
        self.assertIn(version,init)
        self.assertIn(f'MyAppVersion "{version}"',installer)
        self.assertIn(f'v{version}.exe',installer)

if __name__=='__main__': unittest.main(verbosity=2)
