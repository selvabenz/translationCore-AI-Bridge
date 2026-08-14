from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol, Any, Iterable


class LanguagePlugin(Protocol):
    id: str
    display_name: str
    direction: str
    script_name: str
    font_family: str
    def tokenize_target(self, text: str) -> list[str]: ...
    def qa_categories(self) -> list[str]: ...
    def normalization_policy(self) -> dict[str, Any]: ...
    def prompt_guidance(self) -> str: ...


@dataclass
class IndicWhitespacePlugin:
    id: str
    display_name: str
    script_name: str
    font_family: str = 'Nirmala UI'
    direction: str = 'ltr'
    categories: tuple[str, ...] = ('spelling', 'word_form', 'grammar', 'punctuation', 'naturalness')
    guidance: str = 'Respect target-language grammar, idiom, honorific usage, word order, punctuation, and natural discourse. Do not force English word order.'

    def tokenize_target(self, text: str) -> list[str]:
        return [x for x in text.split() if x]

    def qa_categories(self) -> list[str]:
        return list(self.categories)

    def normalization_policy(self) -> dict[str, Any]:
        return {'unicode': 'NFC', 'preserveScriptureSurfaceForms': True}

    def prompt_guidance(self) -> str:
        return self.guidance


@dataclass
class TamilPlugin(IndicWhitespacePlugin):
    id: str = 'ta'
    display_name: str = 'Tamil'
    script_name: str = 'Tamil'
    font_family: str = 'Nirmala UI'
    direction: str = 'ltr'
    categories: tuple[str, ...] = ('spelling', 'word_form', 'grammar', 'sandhi', 'word_joining', 'punctuation', 'naturalness')
    guidance: str = ('Evaluate Tamil grammar, honorific agreement, case suffixes, verbal agreement, spelling, punctuation, '
                     'சந்திப்பிழை / Sandhi, word joining, and naturalness. Tamil suffixes or phrases may legitimately encode Hebrew morphology.')

    def normalization_policy(self) -> dict[str, Any]:
        return {'unicode': 'NFC', 'preserveScriptureSurfaceForms': True, 'sandhiAware': True}


@dataclass
class GenericWhitespacePlugin:
    id: str = 'generic'
    display_name: str = 'Target language'
    direction: str = 'ltr'
    script_name: str = 'Unknown'
    font_family: str = 'Segoe UI'

    def tokenize_target(self, text: str) -> list[str]:
        return [x for x in text.split() if x]

    def qa_categories(self) -> list[str]:
        return ['spelling', 'grammar', 'punctuation', 'naturalness']

    def normalization_policy(self) -> dict[str, Any]:
        return {'unicode': 'NFC', 'preserveScriptureSurfaceForms': True}

    def prompt_guidance(self) -> str:
        return 'Evaluate the detected target language according to its own grammar and idiom. Do not apply Tamil-specific or English-specific rules unless the project language requires them.'


@dataclass
class SourceLanguageDescriptor:
    id: str
    display_name: str
    direction: str = 'rtl'
    script_name: str = 'Hebrew'
    font_family: str = 'Segoe UI'
    morphology_fields: tuple[str, ...] = ('lemma', 'strong', 'morph', 'occurrence', 'occurrences')


@dataclass(frozen=True)
class ProjectLanguageContext:
    target_id: str
    target_name: str
    target_direction: str
    target_script: str
    target_font: str
    source_id: str
    source_name: str
    source_direction: str
    source_script: str
    source_font: str
    qa_categories: tuple[str, ...]
    prompt_guidance: str
    detection_basis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            'target': {'id': self.target_id, 'name': self.target_name, 'direction': self.target_direction, 'script': self.target_script, 'font': self.target_font},
            'source': {'id': self.source_id, 'name': self.source_name, 'direction': self.source_direction, 'script': self.source_script, 'font': self.source_font},
            'qa_categories': list(self.qa_categories),
            'prompt_guidance': self.prompt_guidance,
            'detection_basis': self.detection_basis,
        }


_LANG_ALIASES = {
    'tam': 'ta', 'tamil': 'ta',
    'hin': 'hi', 'hindi': 'hi',
    'mal': 'ml', 'malayalam': 'ml',
    'tel': 'te', 'telugu': 'te',
    'kan': 'kn', 'kannada': 'kn',
    'guj': 'gu', 'gujarati': 'gu',
    'ben': 'bn', 'bengali': 'bn', 'bangla': 'bn',
    'pan': 'pa', 'punjabi': 'pa', 'punjabi (gurmukhi)': 'pa',
}


class PluginRegistry:
    """Language-aware behavior registry.

    Project metadata is authoritative when it declares a target language. Script detection is a
    fallback for incomplete manifests. Source language is inferred from the actual alignment
    topWords first (Hebrew/Greek Unicode), then from book canon as a safe fallback.
    """

    def __init__(self):
        self._plugins: dict[str, LanguagePlugin] = {
            'ta': TamilPlugin(),
            'hi': IndicWhitespacePlugin('hi', 'Hindi', 'Devanagari'),
            'ml': IndicWhitespacePlugin('ml', 'Malayalam', 'Malayalam'),
            'te': IndicWhitespacePlugin('te', 'Telugu', 'Telugu'),
            'kn': IndicWhitespacePlugin('kn', 'Kannada', 'Kannada'),
            'gu': IndicWhitespacePlugin('gu', 'Gujarati', 'Gujarati'),
            'bn': IndicWhitespacePlugin('bn', 'Bengali', 'Bengali'),
            'pa': IndicWhitespacePlugin('pa', 'Punjabi', 'Gurmukhi'),
            'generic': GenericWhitespacePlugin(),
        }
        self._sources = {
            'hbo': SourceLanguageDescriptor('hbo', 'Biblical Hebrew', 'rtl', 'Hebrew', 'Segoe UI'),
            'el-x-koine': SourceLanguageDescriptor('el-x-koine', 'Koine Greek', 'ltr', 'Greek', 'Segoe UI'),
        }

    def normalize_language_id(self, language_id: str | None, name: str | None = None) -> str:
        raw = str(language_id or '').strip().lower().replace('_', '-')
        if raw in self._plugins:
            return raw
        if raw in _LANG_ALIASES:
            return _LANG_ALIASES[raw]
        n = str(name or '').strip().lower()
        if n in _LANG_ALIASES:
            return _LANG_ALIASES[n]
        return raw or 'generic'

    def get(self, language_id: str, name: str | None = None) -> LanguagePlugin:
        key = self.normalize_language_id(language_id, name)
        if key in self._plugins:
            return self._plugins[key]
        return self._plugins['generic']

    def source(self, language_id: str) -> SourceLanguageDescriptor | None:
        return self._sources.get(language_id)

    def register_target(self, plugin: LanguagePlugin):
        self._plugins[str(plugin.id)] = plugin

    def register_source(self, descriptor: SourceLanguageDescriptor):
        self._sources[str(descriptor.id)] = descriptor

    @staticmethod
    def _script_counts(text: str) -> dict[str, int]:
        counts = {'Hebrew': 0, 'Greek': 0, 'Tamil': 0, 'Devanagari': 0, 'Malayalam': 0, 'Telugu': 0, 'Kannada': 0, 'Gujarati': 0, 'Bengali': 0, 'Gurmukhi': 0}
        for ch in text:
            o = ord(ch)
            if 0x0590 <= o <= 0x05FF: counts['Hebrew'] += 1
            elif 0x0370 <= o <= 0x03FF or 0x1F00 <= o <= 0x1FFF: counts['Greek'] += 1
            elif 0x0B80 <= o <= 0x0BFF: counts['Tamil'] += 1
            elif 0x0900 <= o <= 0x097F: counts['Devanagari'] += 1
            elif 0x0D00 <= o <= 0x0D7F: counts['Malayalam'] += 1
            elif 0x0C00 <= o <= 0x0C7F: counts['Telugu'] += 1
            elif 0x0C80 <= o <= 0x0CFF: counts['Kannada'] += 1
            elif 0x0A80 <= o <= 0x0AFF: counts['Gujarati'] += 1
            elif 0x0980 <= o <= 0x09FF: counts['Bengali'] += 1
            elif 0x0A00 <= o <= 0x0A7F: counts['Gurmukhi'] += 1
        return counts

    def detect_target_from_text(self, text: str) -> LanguagePlugin:
        counts = self._script_counts(text)
        script = max(counts, key=counts.get) if counts and max(counts.values(), default=0) else ''
        by_script = {'Tamil': 'ta', 'Devanagari': 'hi', 'Malayalam': 'ml', 'Telugu': 'te', 'Kannada': 'kn', 'Gujarati': 'gu', 'Bengali': 'bn', 'Gurmukhi': 'pa'}
        return self.get(by_script.get(script, 'generic'))

    def detect_source(self, words: Iterable[str] = (), book_id: str = '') -> SourceLanguageDescriptor:
        text = ' '.join(str(x) for x in words)
        counts = self._script_counts(text)
        if counts['Hebrew'] > counts['Greek'] and counts['Hebrew']:
            return self._sources['hbo']
        if counts['Greek'] > counts['Hebrew'] and counts['Greek']:
            return self._sources['el-x-koine']
        # Standard Protestant canon fallback: Matthew onward is Greek, otherwise Hebrew.
        nt = {'mat','mrk','luk','jhn','act','rom','1co','2co','gal','eph','php','col','1th','2th','1ti','2ti','tit','phm','heb','jas','1pe','2pe','1jn','2jn','3jn','jud','rev'}
        return self._sources['el-x-koine' if str(book_id).lower() in nt else 'hbo']

    def detect_project(self, project: Any, alignment: Any | None = None, target_text: str = '') -> ProjectLanguageContext:
        manifest = getattr(project, 'manifest', {}) or {}
        target_meta = manifest.get('target_language') or manifest.get('targetLanguage') or {}
        if not isinstance(target_meta, dict): target_meta = {}
        lang_id = target_meta.get('id') or getattr(getattr(project, 'summary', None), 'language_id', '') or ''
        lang_name = target_meta.get('name') or getattr(getattr(project, 'summary', None), 'language_name', '') or ''
        declared = bool(lang_id or lang_name)
        plugin = self.get(str(lang_id), str(lang_name)) if declared else self.detect_target_from_text(target_text)
        if plugin.id == 'generic' and target_text:
            inferred = self.detect_target_from_text(target_text)
            if inferred.id != 'generic': plugin = inferred
        top_words = []
        if alignment is not None:
            try: top_words = [t.word for t in alignment.all_top()]
            except Exception: top_words = []
        source = self.detect_source(top_words, getattr(project, 'book_id', ''))
        basis = 'manifest target language + source token script' if declared and top_words else 'manifest target language' if declared else 'Unicode script detection'
        display_name = str(lang_name).strip() if declared and plugin.id == 'generic' and lang_name else plugin.display_name
        declared_id = self.normalize_language_id(str(lang_id), str(lang_name)) if declared else plugin.id
        context_id = declared_id if declared_id != 'generic' and plugin.id == 'generic' else plugin.id
        return ProjectLanguageContext(
            target_id=context_id, target_name=display_name, target_direction=plugin.direction,
            target_script=plugin.script_name, target_font=plugin.font_family,
            source_id=source.id, source_name=source.display_name, source_direction=source.direction,
            source_script=source.script_name, source_font=source.font_family,
            qa_categories=tuple(plugin.qa_categories()), prompt_guidance=plugin.prompt_guidance(), detection_basis=basis,
        )

    def list(self) -> list[dict[str, Any]]:
        rows = [{'id': p.id, 'name': p.display_name, 'kind': 'target', 'direction': p.direction, 'script': p.script_name, 'qa': p.qa_categories()} for p in self._plugins.values()]
        rows += [{'id': p.id, 'name': p.display_name, 'kind': 'source', 'direction': p.direction, 'script': p.script_name, 'qa': list(p.morphology_fields)} for p in self._sources.values()]
        return rows
