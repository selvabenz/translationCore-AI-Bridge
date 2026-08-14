# Master Prompt: AI-Enabled translationCore / Bible Translation Review Workbench

I want to build an AI-enabled Bible translation checking application based on the architecture, workflow, and useful concepts of the open-source **translationCore** application.

The goal is **not simply to add a ChatGPT window to translationCore**.

The goal is to create an AI-assisted translation checking environment where AI does the repetitive searching, comparison, resource reading, preselection, analysis, and preparation work, while the **human translator/reviewer remains the final authority**.

The application should particularly support Hebrew → Tamil Bible translation checking, but its architecture should later be reusable for other source and target languages.

---

# 1. Central Principle

The core principle of the application is:

> **AI prepares, analyzes, proposes, explains, prioritizes, and gathers evidence.**
> **Human reviewers decide, edit Scripture, accept or reject findings, resolve discussions, and give final approval.**

AI must never silently change approved Scripture or human-approved project data.

The technical architecture must enforce this rule.

Use:

```
AI
 ↓
AI WORKSPACE / PROPOSALS
 ↓
HUMAN REVIEW
 ↓
APPROVED PROJECT DATA

```

Never:

```
AI
 ↓
PROJECT DATA

```

---

# 2. Existing translationCore Concepts to Preserve

Study and preserve useful translationCore architecture rather than unnecessarily reinventing it.

Important areas include:

```
translationCore/
├── main.js
├── src/
│   ├── js/
│   │   ├── actions/
│   │   │   └── WordAlignmentActions.js
│   │   ├── helpers/
│   │   │   ├── WordAlignmentHelpers.js
│   │   │   ├── ProjectAPI.js
│   │   │   ├── TargetLanguageHelpers.js
│   │   │   ├── originalLanguageResourcesHelpers.js
│   │   │   ├── usfmHelpers.js
│   │   │   ├── manifestHelpers.js
│   │   │   └── checkDataHelpers.js
│   │   └── localStorage/
│   │       ├── loadMethods.js
│   │       └── saveMethods.js
│   │
│   └── tC_apps/
│       ├── wordAlignment/
│       ├── translationNotes/
│       └── translationWords/
│
└── tcResources/

```

translationNotes and translationWords use the shared **checking-tool-wrapper** architecture.

Important concepts that should be preserved:

- `contextId`
- `checkData`
- Translation Notes resources
- Translation Words resources
- Word Alignment
- `topWords`
- `bottomWords`
- selections
- comments
- reminders/discussion
- verse edits
- check invalidation when Scripture changes
- resource versions
- human checking history
- alignment memory
- project manifests
- USFM compatibility

---

# 3. Projects the Application Must Support

Do not assume every project is fresh.

The application must support:

## A. Fresh project

Possibly contains:

- target-language Scripture
- Hebrew/Greek source text
- Translation Notes
- Translation Words
- English reference

but may contain:

- no alignment
- no Translation Note selections
- no Translation Word selections
- no check history

AI can prepare work from scratch.

## B. Partially completed project

May contain:

- some approved alignments
- some missing alignments
- some TN checks
- some TW checks
- comments
- discussions
- verse edits
- incomplete chapters
- mixed states

Existing human work must be preserved.

AI should normally fill gaps rather than overwrite previous work.

## C. Previously reviewed project

May contain extensive human-approved work.

AI may audit it and flag possible problems, but must not automatically modify it.

---

# 4. Project State Detection

When a project opens, first scan it.

Detect:

- Scripture files
- book/chapter/verse availability
- source-language resources
- target-language text
- English reference text
- alignmentData
- checkData
- TN selections
- TW selections
- comments
- discussions
- verse edits
- invalidated checks
- approved terminology
- resource versions
- missing resources
- corrupt/incomplete data

Classify each unit of work as:

```
UNTOUCHED
AI_PREPARED
PARTIALLY_WORKED
HUMAN_APPROVED
HUMAN_EDITED
NEEDS_DISCUSSION
AI_REJECTED
STALE_AFTER_VERSE_EDIT

```

Provide a startup analysis such as:

```
PSALMS PROJECT ANALYSIS

Verses:                    2,461

Word Alignment
Human approved:              824
Partial:                     173
Not started:               1,464

Translation Notes
Completed:                   396
Needs discussion:             12
Not checked:                 987

Translation Words
Completed:                   144
Not checked:                 312

Verse edits detected:         28
Checks requiring recheck:     19

```

Provide options:

```
[ Prepare untouched work ]

[ Recheck changed verses ]

[ Verify existing work ]

[ Full project audit ]

```

Default mode for partially completed projects should normally be:

> **Fill gaps / prepare untouched work.**

---

# 5. Existing Human Work Has Priority

Use this evidence priority:

```
1. Current human-approved project work
2. Human-edited selections/alignments
3. Previous human-approved TN/TW decisions
4. Approved terminology memory
5. Existing approved Word Alignment
6. Hebrew quote + occurrence
7. Hebrew morphology / lemma
8. Translation Notes
9. Translation Words
10. Tamil contextual analysis
11. English reference
12. AI inference

```

Existing approved human work should never be overwritten automatically because AI prefers another interpretation.

AI can flag disagreement for review.

---

# 6. Main Resources

The checker may use:

## Source language

For Psalms:

- UHB Hebrew
- tokens
- lemmas
- morphology
- occurrence information
- source phrase boundaries where available

For future projects:

- Greek equivalent resources

## Target language

Tamil Bible draft/project text.

This Scripture text is authoritative project content and must not be automatically modified by AI.

## English reference

Use as a supporting/reference translation only.

The English translation should not control Hebrew → Tamil analysis.

## Translation Notes

Use:

- reference
- quoted Hebrew/Greek
- occurrence
- support/reference
- translation problem
- explanatory note
- relevant Translation Academy concepts where available

## Translation Words

Use:

- key term
- original-language lemma/word
- definition
- conceptual range
- occurrences
- translation suggestions
- previous approved Tamil renderings

## Alignment

Use:

```
Hebrew topWords
↕
Tamil bottomWords

```

Existing human-approved alignment is strong evidence.

---

# 7. Translation Notes Workflow

Translation Notes should continue to function as a structured human checking workflow.

A Translation Note contains approximately:

```
Reference
Hebrew/Greek quote
Occurrence
Problem
Explanation
Translation advice

```

The existing model asks the reviewer to identify where the issue is represented in the target translation.

The AI-enhanced version should automatically prepare this.

Input to AI:

```
Reference
Hebrew quote
Occurrence
Full Hebrew verse
Hebrew tokenization
Hebrew morphology
Lemma
Translation Note
Problem category
Tamil verse
Existing alignment
Previous TN selections
Translation Word information if relevant
Previous approved terminology
English reference

```

AI output:

```
Proposed Tamil selection
Assessment
Evidence
Potential problem
Suggested action
Confidence

```

The human then chooses:

```
[ ACCEPT ]

[ EDIT SELECTION ]

[ NEEDS DISCUSSION ]

[ REJECT AI ]

```

AI preparation alone must not mark the check completed.

---

# 8. Hebrew Quote → Tamil Selection Engine

This is a major feature.

The application must select the likely Tamil Bible text associated with the quoted Hebrew based on:

- Hebrew quote
- occurrence
- morphology
- lemma
- Translation Note problem
- Translation Note explanation
- existing alignment
- Tamil verse semantics
- Translation Words data
- previous approved decisions

Do not ask AI to freely generate a Tamil phrase.

Tokenize the Tamil verse first.

Example:

```
T0  கர்த்தருக்குப்
T1  பயந்து
T2  அவருக்குச்
T3  சேவை
T4  செய்யுங்கள்

```

AI must return token IDs:

```
{
  "selectedTokenIds": ["T2", "T3", "T4"],
  "confidence": 0.96
}

```

The application reconstructs the selected text.

This prevents AI hallucinating text not actually present in Scripture.

Support:

- one-to-one selection
- one-to-many selection
- many-to-one selection
- phrase alignment
- discontinuous Tamil selections

Do not require the selected words to be consecutive.

---

# 9. Tamil Selection Evidence Priority

Tamil selection should follow this order:

## First

Existing human-approved alignment.

Example:

```
Hebrew:
לְךָ

Existing alignment:
לְךָ → உமக்கு

AI proposed TN selection:
உமக்கு

Confidence:
VERY HIGH

```

## Second

Previously human-approved TN/TW selections.

## Third

Hebrew morphology and semantic context.

## Fourth

Translation Note problem and explanation.

## Fifth

Translation Word definition/concept.

## Sixth

Tamil contextual analysis.

## Seventh

English reference as supporting evidence.

AI inference is the fallback, not the primary evidence.

---

# 10. Word Alignment Workflow

Word Alignment connects source language to Tamil.

Use:

```
Hebrew topWords
     ↕
Tamil bottomWords

```

AI may:

- inspect existing alignments
- detect missing alignment
- detect suspicious alignment
- propose alignment
- explain alignment
- assign confidence
- compare against TN/TW information

AI must not silently approve alignment.

Use visually distinct states:

```
solid line      = HUMAN APPROVED

dotted line     = AI PROPOSED

```

Actions:

```
[ Accept ]

[ Edit ]

[ Needs Discussion ]

[ Reject AI ]

```

---

# 11. Translation Words Workflow

Translation Words should focus on:

- key concepts
- terminology
- semantic consistency
- contextually justified variations
- book-wide usage

Example:

```
Hebrew lemma:
חֶסֶד

Previous approved Tamil:

கிருபை       18
பேரன்பு       3
இரக்கம்       1

```

AI should assess:

```
Current rendering:
கிருபை

Meaning:
Compatible

Terminology:
Matches dominant approved rendering

Context:
Appropriate

Confidence:
95%

```

If there is variation:

```
⚠ TERMINOLOGY REVIEW

Current:
இரக்கம்

Dominant approved rendering:
கிருபை

The difference may be contextually justified.
Review consistency before changing anything.

```

Human makes the terminology decision.

---

# 12. Translation Memory

Only human-approved work becomes trusted translation memory.

Never add raw AI suggestions automatically.

Store useful context including:

```
source lemma
source surface form
reference
source phrase
target phrase
Tamil token IDs
morphology
TN/TW category
semantic context
reviewer
approval status
timestamp
resource version

```

Do not assume:

```
one Hebrew word = one fixed Tamil word

```

Translation memory must remain context-sensitive.

---

# 13. AI Translation QA

AI should eventually check:

## Accuracy

- wrong meaning
- missing meaning
- added meaning
- semantic shift
- mistranslated participant
- wrong referent
- negation
- singular/plural
- person
- gender where relevant
- grammatical relation
- discourse relation
- verbal force where relevant

## Alignment

- missing alignment
- incorrect alignment
- incomplete phrase alignment
- suspicious many-to-one relationship
- wrong occurrence
- unaligned source meaning
- unaligned target addition

## Terminology

- key-term inconsistency
- Translation Word consistency
- contextually justified exceptions
- approved terminology

## Tamil quality

- spelling
- Tamil word-form errors
- grammar
- sentence flow
- punctuation
- சந்திப்பிழை / Sandhi
- word joining
- unnatural constructions
- ambiguous constructions
- translationese

AI should categorize findings by severity.

---

# 14. Severity System

Use:

```
CRITICAL
Meaning changed, omitted, or added materially

HIGH
Wrong participant
negation
number/person
major theological/key-term problem
major alignment error

MEDIUM
Ambiguity
grammar affecting interpretation
terminology inconsistency
potential contextual issue

LOW
Style
punctuation
minor spelling
minor Sandhi issue
word order/naturalness

```

Allow reviewers to filter by severity.

---

# 15. AI Evidence Panel

AI should not simply say:

```
Correct.

```

It should produce evidence.

Example:

```
AI EVIDENCE

✓ Hebrew quote located
  עִבְדוּ

✓ Occurrence
  occurrence 1

✓ Morphology
  imperative

✓ Existing alignment
  עִבְדוּ
      ↓
  ஊழியம் செய்யுங்கள்

✓ Translation Note
  Main semantic issue represented

✓ Translation Word
  Terminology consistent

✓ Previous approved usage
  Same rendering accepted in 4 occurrences

⚠ Possible terminology variation

CONFIDENCE
97%

```

---

# 16. AI Status Model

Use explicit states:

```
⚪ NOT ANALYZED

🔵 AI PROCESSING

🟣 AI PREPARED

🟢 HUMAN ACCEPTED

🟡 NEEDS DISCUSSION

🔴 ISSUE FOUND

⚫ AI REJECTED

↻ STALE / RECHECK REQUIRED

```

Critical rule:

```
AI PREPARED ≠ COMPLETE

```

Only appropriate human approval should produce:

```
HUMAN ACCEPTED = COMPLETE

```

---

# 17. Scripture Editing

AI may suggest edits.

Example:

```
Current Tamil:
...

AI suggestion:
...

Reason:
...

```

But AI must never automatically rewrite Scripture.

Human must explicitly choose something like:

```
[ APPLY EDIT ]

```

Scripture editing actions must support:

- undo
- redo
- history
- before/after comparison
- reviewer identity
- timestamp

---

# 18. Checks Must Become Stale When Scripture Changes

If a human changes a Tamil verse after an alignment/TN/TW check was approved, related checks must be revalidated.

Example:

```
HUMAN APPROVED
      ↓
Tamil verse edited
      ↓
Selection no longer valid
      ↓
STALE / RECHECK REQUIRED

```

AI may reanalyze the changed verse and prepare a new proposal.

Do not leave obsolete checks marked green.

---

# 19. Human Review Actions

Every significant AI proposal should offer:

```
[ ACCEPT ]

[ EDIT ]

[ NEEDS DISCUSSION ]

[ REJECT AI ]

```

## Accept

Human verifies proposal.

Then:

```
AI proposal
→ human accepted
→ approved project/checkData
→ trusted translation memory

```

## Edit

Human changes:

- Tamil token selection
- alignment
- categorization
- terminology decision
- Scripture text where appropriate

Human-edited result becomes authoritative.

## Needs Discussion

Store:

- issue
- evidence
- reviewer comment
- AI proposal
- status
- reference

Do not count as final approval.

## Reject AI

Allow optional reason:

```
wrong Tamil selection
wrong Hebrew interpretation
wrong TN interpretation
wrong TW interpretation
wrong alignment
wrong terminology inference
insufficient context
other

```

Keep rejected proposal in audit history.

---

# 20. Main Review Screen

Build approximately:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ translationCore AI        PSA 2:11                 ● AI Connected           │
├──────────────────────────────────────────────────────────────────────────────┤
│ PROJECT: Tamil       BOOK: Psalms       CH: 2       VERSE: 11    ◀  ▶       │
├───────────────┬──────────────────────────────────────────────┬───────────────┤
│ CHECKS        │ SCRIPTURE                                    │ AI REVIEW     │
│               │                                              │               │
│ ● Alignment   │ HEBREW                                       │ ✓ Prepared    │
│ ● TN          │ Hebrew tokens                                │               │
│ ● TW          │                                              │ Confidence    │
│ ○ Final QA    │ ─────── Alignment ───────                    │ 97%           │
│               │                                              │               │
│               │ TAMIL                                        │ Assessment    │
│               │ Tamil tokenized verse                         │ ✓ Meaning     │
│               │                                              │ ✓ Grammar     │
│               │ ENGLISH REFERENCE                            │ ✓ Alignment   │
│               │ English reference text                        │ ⚠ Terminology │
├───────────────┴──────────────────────────────────────────────┤               │
│ TRANSLATION NOTE                                             │ Evidence      │
│ Hebrew Quote                                                 │ Alignment ✓   │
│ Occurrence                                                   │ TN ✓          │
│ Problem                                                      │ Morphology ✓  │
│ Note                                                         │ TW ✓          │
├──────────────────────────────────────────────────────────────┴───────────────┤
│ AI PROPOSED TAMIL SELECTION                                                 │
│                                                                             │
│ [ selected Tamil token ] [ selected Tamil phrase ]                          │
│                                                                             │
│ [ ACCEPT ] [ EDIT ] [ NEEDS DISCUSSION ] [ REJECT AI ]                     │
└──────────────────────────────────────────────────────────────────────────────┘

```

---

# 21. Hebrew Token Interaction

Hebrew tokens should remain interactive.

Click/hover should show:

```
Hebrew surface form
lemma
morphology
stem
person
number
gender
occurrence
gloss where appropriate
current Tamil alignment
related Translation Notes
related Translation Words
previous approved Tamil renderings

```

Include:

```
[ Explain with AI ]

```

---

# 22. Batch AI Preparation

Allow AI to prepare:

```
current check
verse
chapter
book

```

AI can prepare findings in advance but cannot approve them.

Example:

```
PSA 1:1   ✓ prepared
PSA 1:2   ✓ prepared
PSA 1:3   ⚠ alignment issue
PSA 1:4   ✓ prepared
PSA 1:5   ⚠ terminology
PSA 1:6   🔴 accuracy issue

```

Provide:

```
[ Review Issues First ]

[ Review All ]

```

---

# 23. Final Verse Review

After Alignment + TN + TW:

```
ALIGNMENT
    ✓

TRANSLATION NOTES
    ✓

TRANSLATION WORDS
    ✓

      ↓

AI FULL VERSE REVIEW
      ↓

Accuracy
Completeness
Missing meaning
Added meaning
Grammar
Terminology
Naturalness
Spelling
Sandhi
Punctuation
      ↓

HUMAN FINAL VERSE REVIEW

```

Only the human can finally approve the verse.

---

# 24. Audit History

Record all important actions.

Example:

```
Psalm 2:11

10:43
AI proposed:
T3 + T4

10:45
Reviewer changed:
T2 + T3 + T4

10:46
Reviewer accepted.

Reason:
Tamil realization requires a three-token phrase.

Reviewer:
...

Model:
...

Source resource:
...

Tamil project version:
...

```

Audit data should include:

- original state
- AI proposal
- human modification
- final state
- reason/comment
- timestamp
- reviewer
- AI model
- resource versions

---

# 25. Safe Working Snapshot

When opening an existing project:

```
OPEN PROJECT
     ↓
VALIDATE
     ↓
CREATE SAFE SNAPSHOT / BACKUP
     ↓
SCAN EXISTING WORK
     ↓
AI WORKSPACE
     ↓
HUMAN APPROVAL
     ↓
WRITE APPROVED CHANGES

```

The system should be able to compare:

```
ORIGINAL PROJECT STATE

vs

AI PROPOSED STATE

vs

HUMAN-APPROVED STATE

```

---

# 26. AI Connection

Use the OpenAI API.

Do not hard-code API keys into source code.

Provide a secure API settings screen.

The application should show connection status:

```
● AI Connected

```

AI calls should use structured responses/schema wherever possible.

Separate:

- source data
- prompt/context builder
- AI result
- validation
- human approval
- project write operation

---

# 27. Proposed AI Architecture

Build approximately:

```
src/
└── ai/
    ├── OpenAIClient
    ├── AISettings
    │
    ├── context/
    │   ├── VerseContextBuilder
    │   ├── HebrewContextBuilder
    │   ├── TamilContextBuilder
    │   ├── AlignmentContextBuilder
    │   ├── TranslationNotesContextBuilder
    │   └── TranslationWordsContextBuilder
    │
    ├── alignment/
    │   ├── AIAlignmentService
    │   ├── QuoteResolver
    │   ├── TamilSelectionResolver
    │   ├── ProposalValidator
    │   └── ConfidenceEngine
    │
    ├── review/
    │   ├── AccuracyReview
    │   ├── MissingMeaningReview
    │   ├── AddedMeaningReview
    │   ├── GrammarReview
    │   ├── TerminologyReview
    │   ├── TamilProofreadingReview
    │   └── FinalVerseReview
    │
    ├── schemas/
    │   ├── alignment.schema
    │   ├── tn-review.schema
    │   ├── tw-review.schema
    │   └── qa.schema
    │
    ├── memory/
    │   ├── ApprovedAlignmentMemory
    │   ├── TerminologyMemory
    │   └── TranslationMemory
    │
    └── audit/
        └── AIReviewHistory

```

---

# 28. Build Order

Build in this sequence.

## v0.1 / Phase 1

Project compatibility and read-only foundation.

Support:

- open translationCore project
- fresh project
- partially completed project
- project scan
- resource validation
- Scripture display
- Hebrew
- Tamil
- English reference
- existing Word Alignment
- Translation Notes
- Translation Words
- existing checkData
- project status detection
- safe snapshot/backup

## Phase 2

Read-only AI review.

AI can:

- read all relevant context
- locate Hebrew quote
- analyze morphology
- inspect existing alignment
- analyze TN
- analyze TW
- propose Tamil selection
- prepare evidence
- assign confidence

No project writes.

## Phase 3

AI Tamil Selection Engine.

Implement:

- Tamil tokenization
- token IDs
- phrase selection
- discontinuous selection
- Hebrew quote resolver
- alignment-first resolver
- semantic fallback

## Phase 4

Human review workflow.

Implement:

- Accept
- Edit
- Needs Discussion
- Reject AI
- Undo
- Redo
- comments
- audit history

## Phase 5

AI Word Alignment.

Implement:

- missing alignment detection
- AI alignment proposals
- evidence
- confidence
- human approval

## Phase 6

Translation Words consistency.

Implement:

- key-term memory
- cross-reference comparison
- dominant renderings
- contextual exceptions
- terminology reports

## Phase 7

Full Translation QA.

Implement:

- accuracy
- missing meaning
- added meaning
- grammar
- number/person/gender
- negation
- terminology
- spelling
- Sandhi
- punctuation
- naturalness

## Phase 8

Batch AI preparation.

Support:

- verse
- chapter
- book

## Phase 9

Final review.

Support:

- full verse review
- chapter review
- final human approval

## Phase 10

Reports.

Generate:

- issues report
- discussion report
- terminology report
- alignment report
- TN report
- TW report
- reviewer audit report
- completion report

---

# 29. v0.1 Target

For the first useful version, focus on:

```
Open fresh or existing translationCore project

+

Detect existing work

+

Preserve existing human work

+

Display Hebrew / Tamil / English

+

Display existing Word Alignment

+

Display Translation Notes

+

Display Translation Words

+

AI locate quoted Hebrew

+

AI propose Tamil selection

+

AI evaluate TN/TW issue

+

Evidence + confidence

+

Accept
Edit
Needs Discussion
Reject AI

+

Human-approved checkData

+

Undo / Redo

+

Audit history

```

Do not attempt automatic full Bible translation in v0.1.

The first priority is a safe, reliable, fast **AI-assisted checking workflow**.

---

# 30. Human vs AI Boundary

AI MAY automatically:

- scan projects
- detect project state
- read resources
- locate source quotes
- determine occurrences
- inspect morphology
- inspect existing alignment
- identify likely Tamil equivalents
- preselect Tamil tokens
- analyze Translation Notes
- analyze Translation Words
- check terminology consistency
- compare previous approved decisions
- detect possible errors
- prioritize issues
- gather evidence
- assign confidence
- batch-prepare checks
- propose alignments
- propose Scripture edits
- identify checks made stale by later edits

AI MAY NOT automatically:

- overwrite existing human alignment
- overwrite Scripture
- approve alignment
- mark TN/TW checks as human-completed
- resolve theological/terminology disputes without review
- dismiss significant problems
- change approved terminology silently
- give final verse approval
- give final chapter approval
- overwrite human comments
- delete existing project history

Human MUST:

- review significant AI proposals
- approve/reject alignment
- change selections when needed
- make Scripture edits
- make final terminology decisions
- resolve discussions
- override AI when necessary
- give final verse/chapter/project approval

---

# 31. Development Instruction

When helping me build this application:

1. Do not guess translationCore file formats if source code can be inspected.
2. Study the actual open-source translationCore, translationNotes, translationWords, checking-tool-wrapper, and wordAlignment implementations where relevant.
3. Preserve compatibility wherever practical.
4. Protect existing project data.
5. Treat fresh and partially completed projects as first-class use cases.
6. Prefer existing human-approved evidence over AI inference.
7. Never silently modify Scripture.
8. Keep AI proposals separate until human approval.
9. Use structured AI outputs rather than unpredictable prose whenever possible.
10. Validate all AI-returned token IDs against the actual verse.
11. Never allow AI-generated Tamil text to masquerade as an existing Scripture selection.
12. Add backups, undo/redo, audit history, and stale-check detection.
13. Test every workflow on both fresh and partially completed projects.
14. Make the UI optimized for reviewer speed.
15. Reduce repetitive human reading/searching wherever AI can safely prepare the information.

The goal is:

> **Increase the speed and quality of Bible translation and checking by moving repetitive searching, resource reading, comparison, preselection, and initial analysis to AI, while keeping translation decisions and final approval under human control.**