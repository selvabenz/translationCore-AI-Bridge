from __future__ import annotations

import unittest
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class CertificationIsolationPatchTests(unittest.TestCase):
    def test_windows_runner_uses_disposable_certification_root(self):
        s=(ROOT/'test_windows.bat').read_text('utf-8')
        self.assertIn('certification_fixture.py',s)
        self.assertIn('set "TC_TEST_ROOT=!CERT_ROOT!"',s)
        self.assertIn('EnableDelayedExpansion',s)
        self.assertIn('DISPOSABLE TEST COPY:  !CERT_ROOT!',s)
        self.assertIn('LIVE_TC_ROOT',s)
        self.assertIn('All write-capable tests run ONLY against the disposable copy.',s)

    def test_windows_fixture_uses_junction_not_privileged_symlink(self):
        s=(ROOT/'tests'/'certification_fixture.py').read_text('utf-8')
        self.assertIn("'mklink','/J'",s.replace(' ',''))
        # Knowledge/closed-loop tests must use the portable fixture helper rather than
        # direct os.symlink calls that fail on normal Windows accounts.
        self.assertNotIn('os.symlink(', (ROOT/'tests'/'test_knowledge_base.py').read_text('utf-8'))
        self.assertNotIn('os.symlink(', (ROOT/'tests'/'test_v05_closed_loop.py').read_text('utf-8'))

    def test_certification_requires_supported_python(self):
        cert=(ROOT/'certify_windows.bat').read_text('utf-8')
        setup=(ROOT/'setup_windows.bat').read_text('utf-8')
        self.assertIn('TC_REQUIRE_CERTIFIED_PYTHON=1',cert)
        self.assertIn('Python 3.11 or 3.12',setup)
        self.assertIn('sys.version_info[:2] in ((3,11),(3,12))',setup)

    def test_live_backend_tests_are_capability_based(self):
        core=(ROOT/'tests'/'test_core.py').read_text('utf-8')
        smoke=(ROOT/'tests'/'test_ui_smoke.py').read_text('utf-8')
        self.assertNotIn("self.assertEqual(set(self.projects),{'rut','psa','oba'})",core)
        self.assertNotIn('self.assertEqual(len(app.projects),3)',smoke)
        self.assertIn('Do not assume Obadiah is still untouched',core)

    def test_empty_or_unsafe_fixture_destination_is_rejected(self):
        s=(ROOT/'tests'/'certification_fixture.py').read_text('utf-8')
        self.assertIn("SAFETY REFUSAL: disposable destination path is empty",s)
        self.assertIn("destination equals application directory",s)
        self.assertIn("destination equals live translationCore directory",s)
        self.assertIn("destination is an ancestor of application directory",s)
        self.assertIn("destination is an ancestor of live translationCore directory",s)
        self.assertNotIn("shutil.rmtree(dest",s)

    def test_certifier_calls_runner_by_absolute_script_directory(self):
        s=(ROOT/'certify_windows.bat').read_text('utf-8')
        self.assertIn('call "%~dp0test_windows.bat"',s)

    def test_fixture_rejects_empty_destination_without_touching_app(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source'
            (source/'projects').mkdir(parents=True)
            (source/'resources').mkdir()
            version_before=(ROOT/'VERSION').read_bytes()
            cp=subprocess.run([sys.executable,str(ROOT/'tests'/'certification_fixture.py'),str(source),''],capture_output=True,text=True)
            self.assertNotEqual(cp.returncode,0)
            self.assertIn('SAFETY REFUSAL',cp.stdout+cp.stderr)
            self.assertEqual((ROOT/'VERSION').read_bytes(),version_before)

    def test_fixture_builds_only_explicit_unique_disposable_destination(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            source=base/'live'
            project=source/'projects'/'demo'
            project.mkdir(parents=True)
            (project/'manifest.json').write_text('{"project":{"id":"demo"}}',encoding='utf-8')
            (project/'keep.txt').write_text('LIVE',encoding='utf-8')
            (source/'resources').mkdir()
            (source/'resources'/'resource.txt').write_text('RESOURCE',encoding='utf-8')
            cert_parent=base/'tc_ai_bridge_v073_cert_123_456'
            dest=cert_parent/'translationCore'
            cp=subprocess.run([sys.executable,str(ROOT/'tests'/'certification_fixture.py'),str(source),str(dest)],capture_output=True,text=True)
            self.assertEqual(cp.returncode,0,cp.stdout+cp.stderr)
            self.assertEqual((project/'keep.txt').read_text('utf-8'),'LIVE')
            self.assertEqual((dest/'projects'/'demo'/'keep.txt').read_text('utf-8'),'LIVE')
            self.assertTrue((dest/'.tc_ai_bridge_disposable_certification_fixture').exists())
            self.assertTrue((dest/'resources').exists())

if __name__=='__main__': unittest.main(verbosity=2)
