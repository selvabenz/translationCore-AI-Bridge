from __future__ import annotations

"""Windows production-certification runner.

Tkinter/Tcl is process-global enough that repeatedly creating and destroying many Tk roots
inside one Python process can make CPython/Tk teardown order obscure an otherwise successful
GUI test. Production certification therefore runs non-GUI tests as one suite and every
real-Tk GUI test in its own fresh Python process. A GUI process crash/teardown warning that
changes the process exit code is treated as a hard failure.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def is_real_tk_test(test_id: str) -> bool:
    return (
        test_id.startswith('tests.test_ui_smoke.')
        or test_id.startswith('tests.test_ui_workflows.')
        or '.UIv04Tests.' in test_id
        or '.ResponsiveUITests.' in test_id
    )


def run_test_ids(ids: list[str], label: str) -> bool:
    if not ids:
        return True
    print(f'\n=== {label}: {len(ids)} test(s) ===', flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromNames(ids)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def main() -> int:
    os.chdir(ROOT)
    discovered = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test*.py', top_level_dir=str(ROOT))
    ids = sorted({t.id() for t in flatten(discovered)})
    gui_ids = [x for x in ids if is_real_tk_test(x)]
    core_ids = [x for x in ids if x not in gui_ids]

    if not run_test_ids(core_ids, 'CORE / DATA / PRODUCTION'):
        print('\nCERTIFICATION FAILED in core/data tests.', flush=True)
        return 1

    print(f'\n=== ISOLATED TK GUI TESTS: {len(gui_ids)} test(s) ===', flush=True)
    env = os.environ.copy()
    passed = 0
    for idx, test_id in enumerate(gui_ids, 1):
        print(f'\n--- GUI {idx}/{len(gui_ids)}: {test_id} ---', flush=True)
        try:
            proc = subprocess.run(
                [sys.executable, '-m', 'unittest', '-v', test_id],
                cwd=ROOT,
                env=env,
                check=False,
                timeout=90,
            )
        except subprocess.TimeoutExpired:
            print(f'\nCERTIFICATION FAILED: isolated GUI test exceeded 90 seconds: {test_id}', flush=True)
            return 124
        if proc.returncode != 0:
            print(f'\nCERTIFICATION FAILED: isolated GUI process returned {proc.returncode}: {test_id}', flush=True)
            return proc.returncode or 1
        passed += 1

    print('\n' + '=' * 72, flush=True)
    print(f'WINDOWS CERTIFICATION RESULT: {len(core_ids) + passed}/{len(ids)} TESTS PASSED', flush=True)
    print(f'  Core/data tests: {len(core_ids)}/{len(core_ids)}', flush=True)
    print(f'  Isolated Tk GUI tests: {passed}/{len(gui_ids)}', flush=True)
    print('=' * 72, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
