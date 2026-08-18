from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

# Launched by the Windows test runner before unittest discovery.
# Projects are copied into a disposable fixture; the large resource directory is
# linked with a Windows junction. Safety guards intentionally fail closed.

MARKER = '.tc_ai_bridge_disposable_certification_fixture'


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def link_resources(src: Path, dst: Path) -> None:
    if os.name != 'nt':
        os.symlink(src, dst, target_is_directory=True)
        return
    proc = subprocess.run(
        ['cmd.exe', '/d', '/c', 'mklink', '/J', str(dst), str(src)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not dst.exists():
        raise RuntimeError(
            'Could not create resources junction.\n'
            + (proc.stdout or '')
            + (proc.stderr or '')
        )


def validate_paths(source_raw: str, dest_raw: str) -> tuple[Path, Path, Path]:
    if not source_raw.strip():
        raise SystemExit('SAFETY REFUSAL: source path is empty.')
    if not dest_raw.strip():
        raise SystemExit('SAFETY REFUSAL: disposable destination path is empty.')

    source = Path(source_raw).resolve()
    dest = Path(dest_raw).resolve()
    app_root = Path(__file__).resolve().parents[1]

    if not (source / 'projects').is_dir() or not (source / 'resources').is_dir():
        raise SystemExit(f'Invalid translationCore data root: {source}')

    # Never permit the fixture destination to be the application tree, the live
    # translationCore tree, an ancestor of either, or a child of the live tree.
    unsafe = [
        (dest == app_root, 'destination equals application directory'),
        (_is_relative_to(dest, app_root), 'destination is inside application directory'),
        (_is_relative_to(app_root, dest), 'destination is an ancestor of application directory'),
        (dest == source, 'destination equals live translationCore directory'),
        (_is_relative_to(dest, source), 'destination is inside live translationCore directory'),
        (_is_relative_to(source, dest), 'destination is an ancestor of live translationCore directory'),
    ]
    for condition, reason in unsafe:
        if condition:
            raise SystemExit(f'SAFETY REFUSAL: {reason}: {dest}')

    # The batch runner deliberately creates a uniquely named temporary parent.
    if 'tc_ai_bridge_v073_cert_' not in dest.parent.name.lower():
        raise SystemExit(
            'SAFETY REFUSAL: destination is not inside the expected uniquely named '
            f'certification temp directory: {dest}'
        )
    if dest.name.lower() != 'translationcore':
        raise SystemExit(f'SAFETY REFUSAL: expected destination leaf "translationCore": {dest}')

    return source, dest, app_root


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('source')
    ap.add_argument('dest')
    args = ap.parse_args()
    source, dest, app_root = validate_paths(args.source, args.dest)

    # Never recursively delete an arbitrary pre-existing path. The temp name is
    # expected to be unique. If it exists, fail closed and let the caller choose
    # a different disposable location.
    if dest.exists():
        raise SystemExit(f'SAFETY REFUSAL: disposable destination already exists: {dest}')

    dest.parent.mkdir(parents=True, exist_ok=False)
    dest.mkdir()
    (dest / MARKER).write_text('translationCore AI Bridge disposable certification fixture\n', encoding='utf-8')
    (dest / 'projects').mkdir()

    count = 0
    for src in sorted((source / 'projects').iterdir()):
        if not src.is_dir() or not (src / 'manifest.json').exists():
            continue
        shutil.copytree(src, dest / 'projects' / src.name, ignore=shutil.ignore_patterns('.git'))
        count += 1

    link_resources(source / 'resources', dest / 'resources')
    print(f'Prepared disposable certification fixture: {dest}')
    print(f'Application directory protected: {app_root}')
    print(f'Live backend protected: {source}')
    print(f'Copied {count} project(s); linked resources from: {source / "resources"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
