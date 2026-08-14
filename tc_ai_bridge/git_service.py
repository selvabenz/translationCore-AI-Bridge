from __future__ import annotations

import subprocess
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class GitError(RuntimeError): pass


@dataclass
class GitStatus:
    available: bool
    repository: bool
    branch: str = ''
    dirty: bool = False
    summary: str = ''


class GitService:
    @staticmethod
    def _subprocess_kwargs() -> dict:
        """Run helper processes invisibly in the packaged Windows GUI.

        Git status is refreshed when projects change.  Without CREATE_NO_WINDOW,
        Windows may briefly create a console window for git.exe even when the
        Bridge itself was packaged with --windowed.
        """
        if os.name != 'nt':
            return {}
        kwargs = {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)}
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = getattr(subprocess, 'SW_HIDE', 0)
            kwargs['startupinfo'] = si
        except Exception:
            pass
        return kwargs

    def __init__(self, project_path: Path):
        self.path=Path(project_path).resolve()

    @staticmethod
    def executable_available() -> bool:
        try:
            return subprocess.run(['git','--version'],capture_output=True,text=True,timeout=10,**GitService._subprocess_kwargs()).returncode==0
        except Exception: return False

    def _run(self,*args:str,check:bool=True) -> subprocess.CompletedProcess:
        try:
            cp=subprocess.run(['git','-C',str(self.path),*args],capture_output=True,text=True,timeout=30,**self._subprocess_kwargs())
        except FileNotFoundError as e: raise GitError('Git is not installed or not available on PATH.') from e
        if check and cp.returncode!=0: raise GitError((cp.stderr or cp.stdout or 'git command failed').strip())
        return cp

    def status(self) -> GitStatus:
        if not self.executable_available(): return GitStatus(False,False,summary='Git executable not available')
        inside=self._run('rev-parse','--is-inside-work-tree',check=False)
        if inside.returncode!=0 or inside.stdout.strip()!='true': return GitStatus(True,False,summary='Project is not a Git repository')
        branch_cp=self._run('rev-parse','--abbrev-ref','HEAD',check=False)
        if branch_cp.returncode==0:
            branch=branch_cp.stdout.strip()
        else:
            # An initialized repository has no HEAD commit yet; symbolic-ref still exposes
            # the intended branch and must not make production checkpointing fail.
            branch=self._run('symbolic-ref','--short','HEAD',check=False).stdout.strip() or 'unborn'
        porcelain=self._run('status','--porcelain').stdout
        return GitStatus(True,True,branch,bool(porcelain.strip()),porcelain.strip())

    def checkpoint(self,message:str,paths:Iterable[Path]|None=None,author_name:str='') -> str:
        st=self.status()
        if not st.repository: raise GitError(st.summary or 'Project is not a Git repository')
        if paths:
            rels=[]
            for p in paths:
                p=Path(p).resolve()
                try: rels.append(str(p.relative_to(self.path)))
                except ValueError: continue
            if rels: self._run('add','--',*rels)
        else:
            self._run('add','-A')
        if not self._run('diff','--cached','--quiet',check=False).returncode:
            return ''
        args=['commit','-m',message]
        if author_name:
            args.extend(['--author',f'{author_name} <translationcore-ai-bridge@local>'])
        self._run(*args)
        return self._run('rev-parse','HEAD').stdout.strip()

    def history(self,limit:int=30) -> list[dict[str,str]]:
        st=self.status()
        if not st.repository: return []
        fmt='%H%x1f%h%x1f%an%x1f%ad%x1f%s'
        cp=self._run('log',f'-n{int(limit)}','--date=iso-strict',f'--pretty=format:{fmt}',check=False)
        out=[]
        for line in cp.stdout.splitlines():
            parts=line.split('\x1f')
            if len(parts)==5: out.append(dict(hash=parts[0],short=parts[1],author=parts[2],date=parts[3],subject=parts[4]))
        return out

    def diff(self) -> str:
        st=self.status()
        if not st.repository: return ''
        return self._run('diff','--no-ext-diff','--').stdout
