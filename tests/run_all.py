from __future__ import annotations
import subprocess, sys

commands = [
    [sys.executable, '-m', 'unittest', '-v', 'tests.test_core'],
    [sys.executable, '-m', 'unittest', '-v', 'tests.test_knowledge_base'],
    [sys.executable, '-m', 'unittest', '-v', 'tests.test_v04_workbench.ProjectStateTests'],
]
for cmd in commands:
    r = subprocess.run(cmd)
    if r.returncode:
        raise SystemExit(r.returncode)
print('Core + Knowledge Base + current Project State tests passed.')
