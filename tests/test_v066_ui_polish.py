from __future__ import annotations

import unittest
from unittest.mock import patch

from tc_ai_bridge.git_service import GitService


class V066WindowsPolishTests(unittest.TestCase):
    def test_git_subprocesses_are_hidden_on_windows(self):
        calls=[]
        class CP:
            returncode=0
            stdout='git version 2.0\n'
            stderr=''
        def fake_run(*args,**kwargs):
            calls.append(kwargs); return CP()
        with patch('tc_ai_bridge.git_service.os.name','nt'), patch('tc_ai_bridge.git_service.subprocess.run',side_effect=fake_run):
            self.assertTrue(GitService.executable_available())
        self.assertTrue(calls)
        self.assertTrue(calls[0].get('creationflags',0))

    def test_version_is_066(self):
        import tc_ai_bridge
        self.assertEqual(tc_ai_bridge.__version__,'0.7.0')

if __name__=='__main__':
    unittest.main(verbosity=2)
