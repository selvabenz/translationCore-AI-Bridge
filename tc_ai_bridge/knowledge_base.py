from __future__ import annotations

import json
import re
import hashlib
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from .tc_project import TranslationCoreProject


@dataclass(frozen=True)
class ResourceRef:
    resource: str
    version: str
    provider: str
    path: str
    project_pinned: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceItem:
    kind: str
    title: str
    content: str
    source_path: str = ''
    version: str = ''
    provider: str = ''
    identifier: str = ''
    authoritative: bool = True

    def to_dict(self) -> dict[str, Any]:
        d=asdict(self)
        if self.source_path:
            try:
                p=Path(self.source_path)
                if p.is_file():
                    h=hashlib.sha256(); h.update(p.read_bytes()); d['sha256']=h.hexdigest()
            except Exception:
                pass
        return d


_VERSION_RE = re.compile(r'^v?(\d+)(?:\.(\d+))?')


def _version_key(name: str) -> tuple[int, int, int, str]:
    """Sort resource folders by semantic-ish version, preferring unfoldingWord on ties."""
    m = _VERSION_RE.match(name)
    major = int(m.group(1)) if m else -1
    minor = int(m.group(2) or 0) if m else 0
    provider_score = 2 if name.endswith('_unfoldingWord') else 1 if 'Door43-Catalog' in name else 0
    return (major, minor, provider_score, name)


def _strip_md(text: str, max_chars: int = 12000) -> str:
    # Preserve headings/bullets because they are useful evidence, but normalize whitespace.
    text = text.replace('\ufeff', '').strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + '\n[…truncated by local knowledge-base packer…]'
    return text


class KnowledgeBaseError(RuntimeError):
    pass


class TranslationHelpsKnowledgeBase:
    """
    Resolves translationCore's installed Translation Helps using project-pinned versions first.

    The resolver intentionally does not use a generic vector store. It preserves the graph:
    project check -> TN/TW group -> TA/TW article -> original-language occurrence -> target selection.
    """

    TA_ALIASES = {
        'writing-quotation': 'writing-quotations',
    }
    # Some historic project indexes point to a concept that v87 split into sense-specific articles.
    TW_PREFIX_ALIASES = {
        'call': 'call-',
        'generation': 'generation-',
        'deliver': 'deliver-',
        'like': 'like-',
        'peoplegroup': 'peoplegroup-',
        'time': 'time-',
    }

    def __init__(self, project: TranslationCoreProject):
        self.project = project
        # .../translationCore/projects/<project>
        self.tc_root = project.path.parent.parent
        self.base = self.tc_root / 'resources' / 'en' / 'translationHelps'
        self.bible_base = self.tc_root / 'resources' / 'en' / 'bibles'
        if not self.base.exists():
            raise KnowledgeBaseError(f'Translation Helps folder not found: {self.base}')
        self._resolved: dict[str, ResourceRef] = {}
        self._article_cache: dict[tuple[str, str], list[EvidenceItem]] = {}

    @staticmethod
    def _provider(folder_name: str) -> str:
        if '_' in folder_name:
            return folder_name.split('_', 1)[1]
        return ''

    def _resource_dir(self, resource: str) -> Path:
        return self.base / resource

    def _pick_latest(self, resource: str) -> ResourceRef:
        rd = self._resource_dir(resource)
        candidates = [p for p in rd.iterdir() if p.is_dir()] if rd.exists() else []
        if not candidates:
            raise KnowledgeBaseError(f'No installed {resource} resources found under {rd}')
        chosen = max(candidates, key=lambda p: _version_key(p.name))
        return ResourceRef(resource, chosen.name.split('_', 1)[0], self._provider(chosen.name), str(chosen), False, 'latest compatible installed fallback')

    def _resolve_exact_folder(self, resource: str, folder_name: str, reason: str, pinned: bool) -> ResourceRef | None:
        p = self._resource_dir(resource) / folder_name
        if not p.is_dir():
            return None
        return ResourceRef(resource, folder_name.split('_', 1)[0], self._provider(folder_name), str(p), pinned, reason)

    def resolve(self, resource: str) -> ResourceRef:
        if resource in self._resolved:
            return self._resolved[resource]

        manifest = self.project.manifest
        ref: ResourceRef | None = None
        if resource == 'translationNotes':
            folder = str(manifest.get('tc_en_check_version_translationNotes') or '')
            if folder:
                ref = self._resolve_exact_folder(resource, folder, 'project manifest tc_en_check_version_translationNotes', True)
        elif resource == 'translationWords':
            folder = str(manifest.get('tc_en_check_version_translationWords') or '')
            if folder:
                ref = self._resolve_exact_folder(resource, folder, 'project manifest tc_en_check_version_translationWords', True)
        elif resource == 'translationAcademy':
            # TA should normally match TN major version/provider. Prefer exact matching generation.
            tn = self.resolve('translationNotes')
            exact = f'{tn.version}_{tn.provider}' if tn.provider else tn.version
            ref = self._resolve_exact_folder(resource, exact, f'matched to Translation Notes {tn.version}', tn.project_pinned)
            if ref is None:
                # Match generation even if provider is unavailable.
                rd = self._resource_dir(resource)
                matches = [p for p in rd.iterdir() if p.is_dir() and p.name.startswith(tn.version + '_')] if rd.exists() else []
                if matches:
                    chosen = max(matches, key=lambda p: _version_key(p.name))
                    ref = ResourceRef(resource, tn.version, self._provider(chosen.name), str(chosen), False, f'matched TA generation to TN {tn.version}')
        elif resource == 'translationWordsLinks':
            tw = self.resolve('translationWords')
            exact = f'{tw.version}_{tw.provider}' if tw.provider else tw.version
            ref = self._resolve_exact_folder(resource, exact, f'matched to Translation Words {tw.version}', tw.project_pinned)
            if ref is None:
                rd = self._resource_dir(resource)
                matches = [p for p in rd.iterdir() if p.is_dir() and p.name.startswith(tw.version + '_')] if rd.exists() else []
                if matches:
                    chosen = max(matches, key=lambda p: _version_key(p.name))
                    ref = ResourceRef(resource, tw.version, self._provider(chosen.name), str(chosen), False, f'matched TWL generation to TW {tw.version}')

        if ref is None:
            ref = self._pick_latest(resource)
        self._resolved[resource] = ref
        return ref

    def inventory(self) -> dict[str, Any]:
        resources = {}
        for r in ('translationAcademy', 'translationNotes', 'translationWords', 'translationWordsLinks'):
            try:
                resources[r] = self.resolve(r).to_dict()
            except Exception as e:
                resources[r] = {'error': str(e)}
        return {
            'project': self.project.summary.display_name,
            'project_path': str(self.project.path),
            'resources': resources,
            'original_language_versions': {
                k: v for k, v in self.project.manifest.items() if k.startswith('tc_orig_lang_check_version_')
            },
            'target_language': self.project.manifest.get('target_language', {}),
        }

    def provenance_manifest(self) -> dict[str, Any]:
        """Version/provenance fingerprint without hashing every large resource file.

        We bind evidence to the project-resolved folder and its manifest/config metadata. Individual
        evidence files carry their own SHA-256 in EvidenceItem.to_dict().
        """
        inv=self.inventory(); out={}
        for name,meta in inv.get('resources',{}).items():
            d=dict(meta) if isinstance(meta,dict) else {'value':meta}
            p=Path(str(d.get('path',''))) if d.get('path') else None
            if p and p.exists():
                try:d['directoryMtimeNs']=p.stat().st_mtime_ns
                except Exception:pass
                manifests=[]
                for candidate in ('manifest.json','manifest.yaml','manifest.yml','config.json','package.json'):
                    q=p/candidate
                    if q.exists() and q.is_file():
                        try:
                            h=hashlib.sha256(q.read_bytes()).hexdigest(); manifests.append({'file':candidate,'sha256':h})
                        except Exception:pass
                d['manifests']=manifests
            out[name]=d
        project_manifest=self.project.path/'manifest.json'
        try: project_sha=hashlib.sha256(project_manifest.read_bytes()).hexdigest()
        except Exception: project_sha=''
        return {'resources':out,'originalLanguageVersions':inv.get('original_language_versions',{}),'targetLanguage':inv.get('target_language',{}),'projectManifestSha256':project_sha}

    @staticmethod
    def _read_text(path: Path) -> str:
        return path.read_text(encoding='utf-8-sig', errors='replace')

    def _find_article(self, root: Path, identifier: str) -> list[Path]:
        exact = list(root.rglob(f'{identifier}.md'))
        if exact:
            return sorted(exact)
        return []

    def ta_articles(self, group_id: str) -> list[EvidenceItem]:
        cache_key = ('ta', group_id)
        if cache_key in self._article_cache:
            return self._article_cache[cache_key]
        ref = self.resolve('translationAcademy')
        root = Path(ref.path)
        ids = [group_id]
        alias = self.TA_ALIASES.get(group_id)
        if alias:
            ids.append(alias)
        paths: list[Path] = []
        for ident in ids:
            paths.extend(self._find_article(root, ident))
            if paths:
                break
        authoritative = True
        # Legacy fallback for an identifier removed from current TA.
        if not paths:
            legacy_root = self._resource_dir('translationAcademy')
            older = sorted([p for p in legacy_root.iterdir() if p.is_dir() and p != root], key=lambda p: _version_key(p.name), reverse=True)
            for candidate in older:
                paths = self._find_article(candidate, group_id)
                if paths:
                    authoritative = False
                    break
        items = [
            EvidenceItem('translationAcademy', f'Translation Academy: {p.stem}', _strip_md(self._read_text(p)), str(p), ref.version, ref.provider, p.stem, authoritative)
            for p in paths[:3]
        ]
        self._article_cache[cache_key] = items
        return items

    def tw_articles(self, term_id: str) -> list[EvidenceItem]:
        cache_key = ('tw', term_id)
        if cache_key in self._article_cache:
            return self._article_cache[cache_key]
        ref = self.resolve('translationWords')
        root = Path(ref.path)
        paths = self._find_article(root, term_id)
        authoritative = True
        if not paths and term_id in self.TW_PREFIX_ALIASES:
            prefix = self.TW_PREFIX_ALIASES[term_id]
            paths = sorted(root.rglob(f'{prefix}*.md'))
        # Legacy exact fallback only when current resource cannot resolve it.
        if not paths:
            legacy_root = self._resource_dir('translationWords')
            older = sorted([p for p in legacy_root.iterdir() if p.is_dir() and p != root], key=lambda p: _version_key(p.name), reverse=True)
            for candidate in older:
                paths = self._find_article(candidate, term_id)
                if paths:
                    authoritative = False
                    break
        items = [
            EvidenceItem('translationWords', f'Translation Word: {p.stem}', _strip_md(self._read_text(p)), str(p), ref.version, ref.provider, p.stem, authoritative)
            for p in paths[:6]
        ]
        self._article_cache[cache_key] = items
        return items

    def twl_occurrences(self, term_id: str, max_items: int = 200) -> list[dict[str, Any]]:
        ref = self.resolve('translationWordsLinks')
        root = Path(ref.path)
        found: list[dict[str, Any]] = []
        for category in ('kt', 'names', 'other'):
            p = root / category / 'groups' / self.project.book_id / f'{term_id}.json'
            if p.exists():
                try:
                    data = json.loads(self._read_text(p))
                except Exception:
                    continue
                if isinstance(data, list):
                    for item in data[:max_items]:
                        if isinstance(item, dict):
                            found.append(item)
        return found

    def global_checking_evidence(self) -> list[EvidenceItem]:
        """Translation Academy checking methodology used for whole-verse/project QA."""
        ref=self.resolve('translationAcademy'); root=Path(ref.path)/'checking'
        wanted=[
            ('accuracy-check','Accuracy Checking'),('complete','Completeness'),('clear','Clarity'),
            ('natural','Naturalness'),('acceptable','Acceptability'),('spelling','Spelling'),
            ('punctuation','Punctuation'),('formatting','Formatting'),('alignment-tool','Alignment Checking'),
            ('trans-note-check','Translation Notes Checking'),('important-term-check','Important Terms / Translation Words'),
            ('language-community-check','Language Community Check'),('level3-approval','Final Approval'),
        ]
        out=[]
        for ident,title in wanted:
            p=root/f'{ident}.md'
            if p.exists():
                out.append(EvidenceItem('translationAcademyChecking',f'Translation Academy — {title}',_strip_md(self._read_text(p),8000),str(p),ref.version,ref.provider,ident,True))
        return out

    def reference_bible_text(self, chapter: str | int, verse: str | int) -> list[EvidenceItem]:
        """Return project source translation and ESV (when installed) as secondary evidence, never source authority."""
        items: list[EvidenceItem] = []
        sources = self.project.manifest.get('source_translations') or []
        resource_ids = []
        if isinstance(sources, list):
            for s in sources:
                if isinstance(s, dict) and s.get('language_id') == 'en' and s.get('resource_id'):
                    resource_ids.append(str(s['resource_id']))
        if 'esv' not in resource_ids:
            resource_ids.append('esv')
        seen = set()
        for rid in resource_ids:
            if rid in seen:
                continue
            seen.add(rid)
            base = self.bible_base / rid
            if not base.exists():
                continue
            versions = sorted([p for p in base.iterdir() if p.is_dir()], key=lambda p: _version_key(p.name), reverse=True)
            for vdir in versions:
                p = vdir / self.project.book_id / f'{chapter}.json'
                if not p.exists():
                    continue
                try:
                    data = json.loads(self._read_text(p))
                    text = str(data.get(str(verse), '')) if isinstance(data, dict) else ''
                except Exception:
                    text = ''
                if text:
                    items.append(EvidenceItem('referenceBible', f'{rid.upper()} reference', text, str(p), vdir.name.split('_', 1)[0], self._provider(vdir.name), rid, False))
                    break
        return items

    def evidence_for_check(self, entry: dict[str, Any]) -> list[EvidenceItem]:
        ctx = entry.get('contextId', {}) if isinstance(entry, dict) else {}
        tool = str(ctx.get('tool') or '')
        group = str(ctx.get('groupId') or '')
        quote = str(ctx.get('quoteString') or '')
        note = str(ctx.get('occurrenceNote') or '')
        items: list[EvidenceItem] = []
        if quote:
            items.append(EvidenceItem('originalQuote', 'Original-language quote', quote, identifier=str(ctx.get('checkId') or '')))
        if tool == 'translationNotes':
            if note:
                items.append(EvidenceItem('translationNote', f'Translation Note: {group}', note, identifier=group))
            items.extend(self.ta_articles(group))
        elif tool == 'translationWords':
            items.extend(self.tw_articles(group))
            occurrences = self.twl_occurrences(group)
            if occurrences:
                refs = []
                for x in occurrences[:80]:
                    c = x.get('contextId', {}) if isinstance(x, dict) else {}
                    r = c.get('reference', {}) if isinstance(c, dict) else {}
                    refs.append(f"{r.get('chapter')}:{r.get('verse')} — {c.get('quoteString','')}")
                items.append(EvidenceItem('translationWordsLinks', f'TWL occurrences in {self.project.book_id.upper()}', '\n'.join(refs), version=self.resolve('translationWordsLinks').version, provider=self.resolve('translationWordsLinks').provider, identifier=group))
        return items

    def evidence_pack_for_verse(self, chapter: str | int, verse: str | int, max_chars: int = 50000) -> dict[str, Any]:
        checks = self.project.checks_for_verse(chapter, verse)
        packs = []
        total = 0
        for entry in checks:
            ctx = entry.get('contextId', {})
            ev = []
            for item in self.evidence_for_check(entry):
                d = item.to_dict()
                content = d.get('content', '')
                remaining = max_chars - total
                if remaining <= 0:
                    break
                if len(content) > remaining:
                    d['content'] = content[:remaining] + '\n[…truncated…]'
                total += len(d.get('content', ''))
                ev.append(d)
            packs.append({
                'tool': ctx.get('tool'),
                'groupId': ctx.get('groupId'),
                'checkId': ctx.get('checkId'),
                'source_quote': ctx.get('quoteString'),
                'occurrence': ctx.get('occurrence'),
                'occurrenceNote': ctx.get('occurrenceNote'),
                'existingSelections': entry.get('selections'),
                'nothingToSelect': bool(entry.get('nothingToSelect', False)),
                'invalidated': bool(entry.get('invalidated', False)),
                'evidence': ev,
            })
        return {
            'resource_provenance': self.inventory()['resources'],
            'global_checking_evidence': [x.to_dict() for x in self.global_checking_evidence()],
            'reference_bibles': [x.to_dict() for x in self.reference_bible_text(chapter, verse)],
            'checks': packs,
        }

    def project_term_renderings(self, group_id: str, limit: int = 200) -> list[dict[str, Any]]:
        """Collect existing target selections across the current project for a TW group."""
        out: list[dict[str, Any]] = []
        for e in self.project._load_index_tool('translationWords'):
            ctx = e.get('contextId', {})
            if str(ctx.get('groupId')) != group_id:
                continue
            sel = e.get('selections')
            if sel is False or sel is None:
                continue
            ref = ctx.get('reference', {})
            out.append({
                'reference': f"{ref.get('chapter')}:{ref.get('verse')}",
                'source_quote': ctx.get('quoteString'),
                'selections': sel,
                'nothingToSelect': bool(e.get('nothingToSelect', False)),
                'invalidated': bool(e.get('invalidated', False)),
            })
            if len(out) >= limit:
                break
        return out
