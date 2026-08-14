from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class PsalmFinding:
    severity:str
    code:str
    title:str
    detail:str
    verse:str=''
    evidence:dict[str,Any]|None=None
    def to_dict(self)->dict[str,Any]: return asdict(self)

# Hebrew cantillation clues used only to suggest cola; they are not asserted as a final
# literary analysis. U+0591 is etnahta; U+05C3 sof pasuq marks verse end.
_MAJOR_BREAKS=('֑','׃')
_NEGATION=('לֹא','אַל','אֵין','בְּלִי')
_CONTRAST=('אַךְ','וְלֹא','כִּי אִם')

def _has_any(word,items): return any(x in word for x in items)

def _split_cola(tokens):
    cola=[]; cur=[]
    for t in tokens:
        cur.append(t)
        if _has_any(t.word,_MAJOR_BREAKS):
            cola.append(cur); cur=[]
    if cur: cola.append(cur)
    return cola

def _lemma_set(colon): return {t.lemma for t in colon if getattr(t,'lemma','')}

def analyze_psalm_chapter(project, chapter:str|int)->dict[str,Any]:
    """Specialized, conservative Psalms structure/parallelism QA.

    The module uses source cantillation/verse segmentation, Hebrew lemma repetition, contrast/
    negation clues, alignment density and Tamil punctuation as *review evidence*. It intentionally
    does not claim to infer the final scholarly literary structure automatically.
    """
    findings=[]; verses=[]; repeated={}; structure_candidates=[]
    for vs in project.verses(chapter):
        if str(vs)=='front': continue
        try: a=project.load_verse_alignment(chapter,vs)
        except Exception: continue
        top=a.all_top(); bottom=a.all_bottom(); tamil=project.target_verse_text(chapter,vs)
        lemmas=[t.lemma for t in top if t.lemma]
        for lemma in lemmas: repeated.setdefault(lemma,[]).append(str(vs))
        cola=_split_cola(top); tamil_breaks=len(re.findall(r'[;:—–]|[.!?]|\s[-–—]\s',tamil))
        major_breaks=max(0,len(cola)-1)
        structure_candidates.append({'verse':str(vs),'hebrewColaCandidateCount':len(cola),'tamilBreakHints':tamil_breaks,'hebrewCola':[[t.word for t in c] for c in cola]})

        if major_breaks and tamil_breaks==0 and len(bottom)>=8:
            findings.append(PsalmFinding('medium','PSALM_LINE_CORRESPONDENCE','Possible Hebrew colon boundary not visible in Tamil',f'Hebrew cantillation suggests {len(cola)} colon/line unit(s), while the Tamil verse has no obvious punctuation/line cue. Review whether the poetic relationship is still clear.',str(vs),{'hebrewCola':[[t.word for t in c] for c in cola]}).to_dict())
        if len(top)>=4 and len(bottom)<=1:
            findings.append(PsalmFinding('high','PSALM_COMPRESSION','Strong source-to-target compression in poetic line',f'{len(top)} Hebrew tokens correspond to {len(bottom)} Tamil token(s). Confirm that poetic-line meaning is not lost.',str(vs),{'hebrewTokens':len(top),'tamilTokens':len(bottom)}).to_dict())

        if len(cola)==2:
            l1,l2=_lemma_set(cola[0]),_lemma_set(cola[1]); shared=sorted(l1 & l2)
            neg1=any(_has_any(t.word,_NEGATION) for t in cola[0]); neg2=any(_has_any(t.word,_NEGATION) for t in cola[1])
            contrast=any(_has_any(t.word,_CONTRAST) for t in top)
            if shared:
                findings.append(PsalmFinding('info','PSALM_PARALLEL_LEXICAL','Lexical repetition across two Hebrew cola',f'{len(shared)} lemma(s) recur across the two candidate cola. Review synonymous/reinforcing parallelism and whether the Tamil preserves the relationship.',str(vs),{'sharedLemmas':shared[:20]}).to_dict())
            if neg1 != neg2 or contrast:
                findings.append(PsalmFinding('medium','PSALM_PARALLEL_CONTRAST','Possible antithetic/contrastive parallelism', 'Negation or contrast clues differ across two Hebrew cola. Review whether the Tamil keeps the contrast and its scope.',str(vs),{'negationColon1':neg1,'negationColon2':neg2,'contrastMarker':contrast}).to_dict())

        # Alignment density can reveal a line whose source semantics may be under-represented.
        empty_source_groups=sum(1 for g in a.alignments if g.top_words and not g.bottom_words)
        if empty_source_groups:
            findings.append(PsalmFinding('high','PSALM_UNALIGNED_SOURCE','Unaligned Hebrew material inside poetic verse',f'{empty_source_groups} source alignment group(s) have no Tamil bottomWords. Review before evaluating parallelism/structure.',str(vs),{'unalignedGroups':empty_source_groups}).to_dict())
        verses.append({'verse':str(vs),'hebrewTokens':len(top),'tamilTokens':len(bottom),'hebrewColaCandidateCount':len(cola),'tamilBreakHints':tamil_breaks})

    repetitions=[{'lemma':k,'verses':sorted(set(v),key=lambda x:int(x) if x.isdigit() else 999),'count':len(v)} for k,v in repeated.items() if len(set(v))>=2]
    repetitions.sort(key=lambda x:(-x['count'],x['lemma']))
    return {'bookId':project.book_id,'chapter':str(chapter),'verses':verses,'structureCandidates':structure_candidates,'repeatedHebrewLemmas':repetitions[:100],'findings':findings,'method':'candidate structural/parallelism QA from Hebrew cantillation, lemma repetition, contrast/negation, alignment and Tamil cues; human/scholarly analysis remains authoritative'}
