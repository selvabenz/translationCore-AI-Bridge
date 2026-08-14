from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _is_windows() -> bool:
    return os.name == 'nt'


def link_readonly_tree(src: Path, dst: Path) -> None:
    """Expose a large read-only fixture tree without requiring Windows symlink privilege.

    POSIX uses a directory symlink. Windows first uses a junction (`mklink /J`), which does
    not require SeCreateSymbolicLinkPrivilege on normal local NTFS volumes. Copying is a
    last-resort fallback so certification remains functional on unusual filesystems.
    """
    src = Path(src).resolve()
    dst = Path(dst)
    if dst.exists() or dst.is_symlink():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not _is_windows():
        os.symlink(src, dst, target_is_directory=True)
        return
    try:
        proc = subprocess.run(
            ['cmd.exe', '/d', '/c', 'mklink', '/J', str(dst), str(src)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode == 0 and dst.exists():
            return
    except Exception:
        pass
    # Slow fallback, but safe and privilege-free. This should almost never be reached.
    shutil.copytree(src, dst)


def copy_project(src: Path, dst: Path, *, include_companion: bool = False) -> None:
    ignores = ['.git']
    if not include_companion:
        ignores.append('translationCoreAI')
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*ignores))


def make_lightweight_root(real_root: Path, project_paths: list[Path], *, include_companion: bool = False):
    """Return (TemporaryDirectory, translationCore root) using copied projects + linked resources."""
    td = tempfile.TemporaryDirectory()
    tc = Path(td.name) / 'translationCore'
    (tc / 'projects').mkdir(parents=True)
    for src in project_paths:
        copy_project(src, tc / 'projects' / src.name, include_companion=include_companion)
    resources = Path(real_root) / 'resources'
    if resources.exists():
        link_readonly_tree(resources, tc / 'resources')
    return td, tc


def find_project(projects: dict[str, object], preferred: str | None = None, *, require_checks: bool = False):
    if preferred and preferred in projects:
        p = projects[preferred]
        if not require_checks or sum(p.index_tools().values()) > 0:
            return p
    for p in projects.values():
        if not require_checks or sum(p.index_tools().values()) > 0:
            return p
    raise AssertionError('No suitable translationCore project found in certification fixture')


def find_numbered_verse(project, *, require_bottom: bool = True):
    for ch in project.chapters():
        for vs in project.verses(ch):
            if vs == 'front':
                continue
            a = project.load_verse_alignment(ch, vs)
            if not require_bottom:
                return str(ch), str(vs), a
            # Any target token can be aligned or in the word bank.
            from tc_ai_bridge.alignment_engine import make_inventory
            inv = make_inventory(a)
            if inv.bottom:
                return str(ch), str(vs), a
    raise AssertionError(f'No suitable numbered verse found in {project.book_id}')
