from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]

class V065PackagingTests(unittest.TestCase):
    def test_runtime_remains_standard_library_only(self):
        req=(ROOT/'requirements.txt').read_text('utf-8').lower()
        self.assertNotIn('pillow',req)
        self.assertNotIn('pyinstaller',req)

    def test_installer_is_per_user_and_requires_no_python(self):
        s=(ROOT/'installer'/'translationCore-AI-Bridge.iss').read_text('utf-8')
        self.assertIn('{localappdata}\\Programs\\translationCore AI Bridge',s)
        self.assertIn('PrivilegesRequired=lowest',s)
        self.assertIn('MinVersion=10.0',s)
        self.assertNotIn('python.exe',s.lower())

    def test_icon_tool_generates_all_consumed_assets(self):
        s=(ROOT/'tools'/'set_app_icon.py').read_text('utf-8')
        for name in ('app_icon.ico','app_icon.png','app_icon_48.png'):
            self.assertIn(name,s)
        self.assertIn("userguide / 'app_icon_48.png'",s)
        ui=(ROOT/'tc_ai_bridge'/'ui.py').read_text('utf-8')
        self.assertIn("app_icon_48.png",ui)
        build=(ROOT/'build_windows_exe.bat').read_text('utf-8')
        self.assertIn('assets\\app_icon.ico',build)
        iss=(ROOT/'installer'/'translationCore-AI-Bridge.iss').read_text('utf-8')
        self.assertIn('app_icon.ico',iss)

    def test_icon_pillow_is_build_time_only(self):
        bat=(ROOT/'set_app_icon.bat').read_text('utf-8').lower()
        self.assertIn('.venv-icon',bat)
        self.assertIn('pillow',bat)
        self.assertNotIn('pillow',(ROOT/'requirements.txt').read_text('utf-8').lower())

    def test_version_consistency(self):
        version=(ROOT/'VERSION').read_text('utf-8').strip()
        self.assertEqual(version,'0.7.5')
        self.assertIn('0.7.5',(ROOT/'installer'/'translationCore-AI-Bridge.iss').read_text('utf-8'))
        self.assertIn('v0.7.5',(ROOT/'tc_ai_bridge'/'ui.py').read_text('utf-8'))

if __name__=='__main__': unittest.main()
