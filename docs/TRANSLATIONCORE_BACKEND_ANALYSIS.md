# translationCore Backend Analysis

This catalog was generated from the uploaded backend and is used as the compatibility baseline for v0.1. The application does **not** hard-code one book: it detects capabilities from each project.

## Backend structure observed

```text
translationCore/
├─ projects/
│  └─ <project>/
│     ├─ manifest.json
│     ├─ <book>.usfm
│     ├─ <book>/<chapter>.json
│     └─ .apps/translationCore/
│        ├─ alignmentData/<book>/<chapter>.json
│        ├─ checkData/{selections,invalidated,comments,verseEdits}/...
│        ├─ index/{wordAlignment,translationNotes,translationWords}/<book>/
│        └─ tools/wordAlignment/{completed,invalid}/...
├─ resources/
│  ├─ hbo/bibles/uhb/
│  ├─ el-x-koine/bibles/ugnt/
│  └─ en/{bibles,translationHelps,lexicons}/...
├─ imports/
└─ logs/
```

## Projects exercised by the test suite

### Obadiah (`ta_ntb_oba_book`)

- Book ID: `oba`; target: Tamil; tC data version: 8; tC edit version: 3.7.0
- Alignment: 1 chapter file(s), 22 verse entries, 291 alignment groups, 364 wordBank tokens
- checkData: `{'invalidated': 1, 'selections': 1}`
- indexes: `{'translationWords': 63, 'wordAlignment': 2, 'translationNotes': 36}`

### Psalms (`ta_ntb_psa_book`)

- Book ID: `psa`; target: தமிழ்; tC data version: 8; tC edit version: 3.7.0
- Alignment: 150 chapter file(s), 2611 verse entries, 19531 alignment groups, 24877 wordBank tokens
- checkData: `{'verseEdits': 4}`
- indexes: `{'translationWords': 246, 'wordAlignment': 151, 'translationNotes': 6}`

### Ruth (`ta_ntb_rut_book`)

- Book ID: `rut`; target: Tamil; tC data version: 8; tC edit version: 3.7.0
- Alignment: 4 chapter file(s), 89 verse entries, 449 alignment groups, 11 wordBank tokens
- checkData: `{'verseEdits': 2, 'comments': 18, 'invalidated': 583, 'selections': 583}`
- indexes: `{'translationWords': 86, 'wordAlignment': 5, 'translationNotes': 59}`

## translationCore check-state folders observed

`comments`, `invalidated`, `selections`, `verseEdits`

## Indexed tools observed

`translationNotes`, `translationWords`, `wordAlignment`

## Translation Notes group IDs observed (62)

`figs-123person`, `figs-abstractnouns`, `figs-activepassive`, `figs-aside`, `figs-doublenegatives`, `figs-doublet`, `figs-ellipsis`, `figs-euphemism`, `figs-exclamations`, `figs-exclusive`, `figs-explicit`, `figs-extrainfo`, `figs-gendernotations`, `figs-hendiadys`, `figs-hyperbole`, `figs-idiom`, `figs-imperative`, `figs-infostructure`, `figs-litany`, `figs-litotes`, `figs-metaphor`, `figs-metonymy`, `figs-nominaladj`, `figs-parallelism`, `figs-personification`, `figs-possession`, `figs-pronouns`, `figs-quotations`, `figs-quotesinquotes`, `figs-reduplication`, `figs-rpronouns`, `figs-rquestion`, `figs-synecdoche`, `figs-you`, `figs-youcrowd`, `figs-youdual`, `figs-yousingular`, `grammar-collectivenouns`, `grammar-connect-exceptions`, `grammar-connect-logic-contrast`, `grammar-connect-logic-goal`, `grammar-connect-logic-result`, `grammar-connect-time-background`, `grammar-connect-time-simultaneous`, `grammar-connect-words-phrases`, `translate-blessing`, `translate-bvolume`, `translate-kinship`, `translate-names`, `translate-plural`, `translate-symaction`, `translate-tense`, `translate-textvariants`, `translate-unknown`, `writing-background`, `writing-endofstory`, `writing-newevent`, `writing-oathformula`, `writing-participants`, `writing-politeness`, `writing-pronouns`, `writing-quotations`

## Translation Words group IDs observed (287)

`aaron`, `abimelech`, `abraham`, `absalom`, `adam`, `adversary`, `afflict`, `age`, `almighty`, `altar`, `amen`, `amorite`, `anoint`, `appoint`, `arkofthecovenant`, `asaph`, `assembly`, `assyria`, `avenge`, `babylon`, `barley`, `barren`, `bashan`, `bathsheba`, `bear`, `beast`, `benjamin`, `bethlehem`, `biblicaltimeday`, `biblicaltimeyear`, `birthright`, `bless`, `blotout`, `boaz`, `bow`, `bowweapon`, `bread`, `bronze`, `burntoffering`, `bury`, `call`, `canaan`, `captive`, `cedar`, `cherubim`, `chief`, `circumcise`, `clan`, `clean`, `comfort`, `companion`, `conceive`, `confess`, `confirm`, `consume`, `counselor`, `courage`, `covenant`, `covenantfaith`, `cow`, `cry`, `curse`, `curtain`, `cutoff`, `daughterofzion`, `david`, `dayofthelord`, `deceive`, `declare`, `decree`, `delight`, `deliverer`, `desert`, `destroyer`, `devour`, `dominion`, `eagle`, `earth`, `edom`, `egypt`, `elder`, `ephraim`, `ephrathah`, `esau`, `eternity`, `ethiopia`, `evil`, `exalt`, `exile`, `faithful`, `falsegod`, `family`, `famine`, `fast`, `favor`, `fear`, `feast`, `fig`, `firstborn`, `firstfruit`, `flock`, `foreigner`, `forsaken`, `foundation`, `freewilloffering`, `fruit`, `gate`, `generation`, `gilead`, `gird`, `glean`, `glory`, `god`, `gold`, `good`, `grace`, `grain`, `grainoffering`, `grape`, `guilt`, `ham`, `hang`, `harvest`, `heaven`, `holy`, `honor`, `hope`, `horse`, `house`, `household`, `inherit`, `iniquity`, `innocent`, `instruct`, `israel`, `jacob`, `jerusalem`, `jesse`, `joab`, `jordanriver`, `josephot`, `joy`, `judah`, `judea`, `judge`, `judgeposition`, `justice`, `kedar`, `kin`, `king`, `kingdom`, `kiss`, `know`, `korah`, `labor`, `lawofmoses`, `leah`, `lebanon`, `leviathan`, `levite`, `lion`, `lord`, `lordyahweh`, `lot`, `lots`, `love`, `majesty`, `manna`, `meditate`, `melchizedek`, `mercy`, `messenger`, `mighty`, `minister`, `miracle`, `moab`, `moses`, `naphtali`, `nathan`, `nation`, `negev`, `neighbor`, `noble`, `oath`, `obadiah`, `olive`, `ordinance`, `overseer`, `peace`, `peoplegroup`, `peopleofgod`, `perish`, `persecute`, `pharaoh`, `philistia`, `philistines`, `phinehas`, `pillar`, `plead`, `possess`, `praise`, `pray`, `preach`, `priest`, `prince`, `prophet`, `prosper`, `prostitute`, `proud`, `prudent`, `punish`, `purify`, `queen`, `rachel`, `rebel`, `rebuke`, `redeem`, `refuge`, `remnant`, `renown`, `report`, `restore`, `reward`, `righteous`, `robe`, `ruler`, `ruth`, `sabbath`, `sackcloth`, `sacrifice`, `samaria`, `samuel`, `sanctuary`, `sandal`, `saul`, `save`, `savior`, `scribe`, `seed`, `seek`, `servant`, `shame`, `sheep`, `sign`, `silver`, `sin`, `slaughter`, `snare`, `solomon`, `spirit`, `statute`, `sword`, `tabernacle`, `tamar`, `tarshish`, `temple`, `terror`, `testimony`, `thief`, `thresh`, `throne`, `tomb`, `tongue`, `tremble`, `tribe`, `trouble`, `trumpet`, `tyre`, `understand`, `vine`, `vineyard`, `virgin`, `vision`, `waste`, `watch`, `wheat`, `wine`, `winnow`, `wise`, `wisemen`, `womb`, `worship`, `wrath`, `wrong`, `yahweh`, `zealous`, `zion`

## v0.1 compatibility behavior

- Reads the real `alignmentData` schema (`topWords`, `bottomWords`, `wordBank`) including Hebrew Strong, lemma, morphology, occurrence and occurrences.
- Reads Translation Notes/Words indexes generically by `contextId`, so newly loaded tC group IDs can appear without an application update.
- Reads selection, invalidation, comment and verse-edit state per verse when present.
- Does not assume every book has every index. Missing/sparse indexes are treated as a capability state, not an error.
- Writes only approved alignmentData and the companion `.apps/translationCoreAI` review/backup files. USFM, target chapter text, source resources, logs and tC check files remain read-only.
