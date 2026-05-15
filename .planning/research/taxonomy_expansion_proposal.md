# Taxonomy Expansion Proposal — Bible RAG v2

**Date**: 2026-05-15
**Author**: Research pass (Claude)
**Status**: Proposal — pending review before seed-content generation
**Scope**: Expand unit types from 16 → ~40

---

## 1. Motivation

The current 16-type taxonomy (`seed, symbol, motif, person, place, number, title, structure, covenant, festival, miracle, parable, prophecy, theophany, office, lexeme`) covers nouns and named institutions extremely well, but under-represents three large phenomena classes that are central to how Scripture actually *means*:

1. **Literary form** — chiasm, inclusio, acrostic, gematria, parallelism. These are the *shape* of the text, and any pattern-discovery RAG that ignores them will produce thin reads on Hebrew narrative and Hebrew poetry alike.
2. **Speech-act / rhetorical mode** — lament, oath, blessing, curse, doxology, beatitude, woe, riddle, taunt. These are the *force* of an utterance, and they are how the prophets, psalmists, and Jesus actually *do things with words*.
3. **Hermeneutic relations** — typology, antitype, recapitulation, reversal, anti-motif. These are the connective tissue between Testaments and within a single book, and they are precisely the patterns the project most wants to surface.

Adding **~24 new types** brings the taxonomy to ~40 and unlocks edges that the current schema can only approximate as `foreshadows` or generic `cross_reference`. Where helpful below we also propose **new edge types** that should be added to `edge.kind` alongside the new unit types.

The proposal is organized in five groups: **Literary Devices, Rhetorical Acts, Narrative Forms, Hermeneutic Markers, and Anti-Motif / Liturgical**. Total: **24 new types**.

---

## 2. Group A — Literary Devices (7 types)

These describe the *shape* of a passage. They are necessarily multi-verse units that span a range; the existing `structure` type collapses these into one bucket, losing the distinction between (e.g.) a chiasm and an inclusio, which behave very differently for retrieval.

### A1. `chiasm`
**Definition.** A symmetrical A-B-C-...-C'-B'-A' pattern in which the *center* carries the rhetorical weight.
**Why current types miss it.** `structure` is too coarse — a chiasm is a *retrievable pivot point*, not just shape.
**Examples.**
- Genesis 17 (covenant renewal, ABCDC'B'A' around the name change).
- The Flood narrative, Gen 6:10–9:19 (Dorsey's macro-chiasm; ark afloat at the center).
- Mark's gospel as a whole (Peter's confession at 8:29 as hinge).
- Leviticus (Day of Atonement at chapter 16 as the book's center).
- Matthew 23's seven woes (concentric structure around hypocrisy).
**Suggested edges.**
- `centered_on` : chiasm → verse / seed (the pivot)
- `mirrors` : verse → verse (paired arms of the chiasm)
- `contains_chiasm` : pericope → chiasm

### A2. `inclusio`
**Definition.** A bracketing device where the same phrase, image, or motif opens and closes a unit ("envelope structure").
**Why current types miss it.** `motif` flags the repeated element but not the *bracketing function* — that the repetition *delimits* a unit.
**Examples.**
- "Vanity of vanities" framing Ecclesiastes (1:2 / 12:8).
- Psalm 8 ("How majestic is your name" at v.1 and v.9).
- Psalm 103 ("Bless the LORD, O my soul").
- "Be fruitful and multiply" framing Gen 1 → Gen 9.
- "The Word" opening and closing the Johannine prologue (John 1:1 / 1:18).
**Suggested edges.**
- `brackets` : inclusio → pericope
- `opens_with` / `closes_with` : inclusio → verse

### A3. `parallelism`
**Definition.** Hebrew-poetic pairing of clauses (synonymous, antithetic, synthetic, climactic). The *engine* of Psalms and Proverbs.
**Why current types miss it.** Currently no way to mark a verse as a parallel pair; lexeme-level repetition misses the syntactic shape.
**Examples.**
- Psalm 19:1 ("The heavens declare... the firmament shows").
- Proverbs 10:1 (antithetic — wise son / foolish son).
- Psalm 1:1 (climactic — walks/stands/sits, counsel/way/seat).
- Isaiah 1:3 (ox/ass, owner/manger — antithetic with Israel).
- Job 3:3 (the day perish / the night declare).
**Suggested edges.**
- `parallels` : verse-line → verse-line
- `subtype` field: synonymous | antithetic | synthetic | climactic | emblematic

### A4. `hapax-legomenon`
**Definition.** A word appearing only once in a corpus (whole Bible, or single book). High exegetical weight per token.
**Why current types miss it.** `lexeme` records the word but not the *uniqueness signal* — which is precisely what makes hapaxes worth retrieving.
**Examples.**
- *tehom-rabbah* nuances in Gen 7:11 (uncommon collocation).
- *tohu wa-bohu* (Gen 1:2) — paired hapax outside Jer 4:23 and Isa 34:11.
- *gopher* (wood, Gen 6:14) — only Bible occurrence.
- *Selah* as semantic hapax outside Psalms / Habakkuk 3.
- *machmaddim* ("delights", Song 5:16).
**Suggested edges.**
- `unique_in` : hapax-legomenon → book / corpus
- `co_occurs_with` : hapax → hapax (when paired hapaxes cluster, e.g. *tohu wa-bohu*).

### A5. `gematria`
**Definition.** A numerical value computed from letters of a word/name, often used typologically.
**Why current types miss it.** `number` is for the surface integer (e.g., 144,000); gematria is a *derived* number from a *name* and needs to link both.
**Examples.**
- 666 = *Neron Caesar* (Rev 13:18).
- 318 = Eliezer's name = Abraham's trained men (Gen 14:14, per the Epistle of Barnabas).
- 14 = David (*DWD*: 4+6+4), structuring Matthew's genealogy (Matt 1:17).
- 888 = *Iēsous* in Greek.
- The Tetragrammaton-related 26 patterns in Hebrew acrostics.
**Suggested edges.**
- `computes_to` : gematria → number
- `encodes` : gematria → person / title

### A6. `acrostic`
**Definition.** A unit whose successive lines begin with the letters of an alphabet in order. Pure form, often signaling *completeness*.
**Why current types miss it.** Currently invisible — no way to surface that Psalm 119 is alphabetic, which is the single most important fact about it.
**Examples.**
- Psalm 119 (8 verses per Hebrew letter).
- Psalms 9–10 (combined acrostic).
- Psalm 25, 34, 37, 145.
- Lamentations 1, 2, 3 (chapter 3 with triple aleph-aleph-aleph).
- Proverbs 31:10–31 (woman of valor).
**Suggested edges.**
- `alphabet` : acrostic → lexeme (the letter)
- `completeness_marker` : acrostic → seed (theme of totality)

### A7. `wordplay` (subsuming paronomasia)
**Definition.** Phonological play — pun, alliteration, assonance, sound-similarity that carries meaning across roots.
**Why current types miss it.** `lexeme` captures the root, but wordplay is *cross-root* and depends on *sound*, not lemma.
**Examples.**
- *adam / adamah* (man / ground, Gen 2:7).
- *isha / ish* (woman / man, Gen 2:23).
- *qayin / qana* (Cain / I have gotten, Gen 4:1).
- *babel / balal* (Babylon / confuse, Gen 11:9).
- Amos 8:1–2: *qayitz* (summer fruit) / *qetz* (end).
**Suggested edges.**
- `puns_on` : wordplay → lexeme (the two roots)
- `realized_in` : wordplay → verse

---

## 3. Group B — Rhetorical / Speech-Act Types (7 types)

These describe *what an utterance is doing*. Current types capture *content* (covenant, miracle, parable) but not *force* (oath, blessing, curse, lament). A "blessing" and a "curse" are formally inverses of each other and must be linkable.

### B1. `lament`
**Definition.** A structured cry of grief or protest to God; typically has address, complaint, petition, expression of trust, vow of praise.
**Why current types miss it.** The lament *form* is invisible — Ps 22 currently can only be tagged via its messianic motifs, not its lament structure.
**Examples.**
- Psalm 22 (foundational individual lament).
- Psalm 88 (lament without resolution).
- Lamentations 1–5.
- Habakkuk 1:2–4 ("How long, O LORD?").
- Jesus in Gethsemane (Matt 26:38–39) and on the cross (Matt 27:46).
**Suggested edges.**
- `cries_to` : lament → person (the addressee)
- `voices` : lament → seed (the underlying theme — exile, suffering, abandonment).

### B2. `oath`
**Definition.** A binding self-malediction or divine-witness invocation. Distinct from a covenant (which is the *agreement*) — the oath is the *sealing speech-act*.
**Why current types miss it.** `covenant` covers the institutional bond; oaths happen *inside* covenants and also outside them.
**Examples.**
- Gen 22:16 ("By myself I have sworn").
- Gen 24:2–3 (Abraham's servant, hand under thigh).
- Heb 6:13–18 (theology of God's oath).
- Matt 26:63–64 (Caiaphas adjuring Jesus under oath).
- The "as I live, says the LORD" formula (Num 14:21; Ezek 33:11).
**Suggested edges.**
- `sworn_by` : oath → person
- `seals` : oath → covenant

### B3. `doxology`
**Definition.** A short ascription of glory to God, often at the close of a unit or book.
**Why current types miss it.** Closing doxologies (Romans 16:25–27; the four book-divisions of Psalms) currently have no form-tag.
**Examples.**
- Romans 11:33–36.
- Romans 16:25–27.
- Ephesians 3:20–21.
- Jude 24–25.
- The four "blessed be the LORD" doxologies dividing the Psalter (41:13; 72:18–19; 89:52; 106:48).
**Suggested edges.**
- `closes` : doxology → pericope / book
- `ascribes` : doxology → title (e.g., "King eternal").

### B4. `beatitude`
**Definition.** A formal "Blessed is/are X" pronouncement.
**Why current types miss it.** Currently flattened into `blessing` or generic motif; the *form* (μακάριος / *ashrei*) is its own genre.
**Examples.**
- Matthew 5:3–12 (the eight/nine).
- Luke 6:20–22.
- Psalm 1:1 ("*Ashrei* the man").
- Revelation 1:3 and the six other Revelation beatitudes.
- James 1:12.
**Suggested edges.**
- `pronounces_on` : beatitude → person/group
- `reverses` : beatitude → woe (Matthean beatitudes ↔ Lucan woes).

### B5. `woe`
**Definition.** Formal lamentational denunciation ("Woe to...").
**Why current types miss it.** Companion to beatitude; currently no way to link Matt 23:13–36 (seven woes) to Isaiah 5:8–22 (six woes).
**Examples.**
- Isaiah 5:8–22 (six woes).
- Habakkuk 2:6–20 (five woes).
- Matthew 23:13–36 (seven woes on the Pharisees).
- Luke 6:24–26.
- Revelation 8:13 (the three eagle-woes).
**Suggested edges.**
- `denounces` : woe → person / group / sin
- `paired_with` : woe → beatitude

### B6. `blessing` / `curse` (pair, treat as two types: `blessing-form`, `curse-form`)
**Definition.** Performative invocation of weal or harm. Distinct from beatitude (which describes the blessed state); these *enact*.
**Why current types miss it.** Theologically distinct from beatitudes; they are *covenantally* loaded (Deut 27–28).
**Examples (blessing).**
- Gen 12:2–3 (Abrahamic).
- Num 6:24–26 (Aaronic).
- Deut 28:1–14.
- Eph 1:3–14.
- The patriarchal blessings (Gen 27, 49).
**Examples (curse).**
- Gen 3:14–19.
- Deut 27:15–26 (twelve curses).
- Joshua 6:26 (Jericho curse — fulfilled in 1 Kgs 16:34).
- Gal 3:10–13.
- The imprecatory psalms (e.g., Ps 109).
**Suggested edges.**
- `invokes_on` : blessing/curse → person
- `inverts` : blessing ↔ curse (paired in Deut 27–28 structure).

### B7. `riddle` / `taunt` (merge as `enigma`)
**Definition.** A speech-act designed to provoke insight (riddle) or shame (taunt). Often poetic.
**Why current types miss it.** No category captures Samson's riddle, the *mashal* against Babylon, or the wisdom riddles of Proverbs 30.
**Examples.**
- Samson's riddle (Judges 14:14).
- Isaiah 14:4–23 (taunt-song against the king of Babylon).
- Habakkuk 2:6 ("Will not all these take up a taunt against him?").
- Proverbs 30:18–19 ("Three things... yea, four").
- Jesus' "destroy this temple" (John 2:19) functioning as enigma.
**Suggested edges.**
- `solved_by` : enigma → person / seed
- `mocks` : taunt → person / nation

---

## 4. Group C — Narrative Forms (5 types)

These are recurring narrative shapes. Currently `pericope` is the only narrative unit and it does not distinguish a call-narrative from a genealogy.

### C1. `dream`
**Definition.** Divine communication via sleep-vision, often requiring interpretation.
**Why current types miss it.** Distinct from `theophany` (waking divine encounter) and `prophecy` (proclaimed oracle); dreams have their own narrative grammar.
**Examples.**
- Jacob's ladder (Gen 28:10–22).
- Joseph's two dreams (Gen 37:5–11) and Pharaoh's (Gen 41).
- Daniel 2 and 4 (Nebuchadnezzar) and Daniel 7 (Daniel himself).
- Joseph the husband of Mary (Matt 1:20; 2:13, 19, 22).
- The Magi (Matt 2:12).
**Suggested edges.**
- `dreamt_by` : dream → person
- `interpreted_by` : dream → person
- `prefigures` : dream → pericope

### C2. `vision`
**Definition.** Waking apocalyptic or prophetic seeing (often labeled *chazon*, *mar'ah*, ὅραμα, ἀποκάλυψις).
**Why current types miss it.** Currently collapsed under `prophecy` or `theophany`; visions have a distinct genre (Ezek 1, Dan 7–12, Rev) with their own bestiary.
**Examples.**
- Isaiah 6 (throne vision).
- Ezekiel 1 (chariot / *merkavah*).
- Daniel 7 (four beasts).
- Acts 10:9–16 (Peter's sheet).
- Revelation 4–5 (throne and Lamb).
**Suggested edges.**
- `seen_by` : vision → person
- `depicts` : vision → symbol / motif

### C3. `genealogy`
**Definition.** A *toledot* or "begats" list, with structural-theological function.
**Why current types miss it.** Genealogies are not pericopes in the narrative sense; they are *structural skeletons* with their own conventions (skipped generations, gematric counts, named women).
**Examples.**
- Gen 5 (Seth-line, ten generations to Noah).
- Gen 11 (Shem-line, ten generations to Abraham).
- Matthew 1:1–17 (three sets of fourteen).
- Luke 3:23–38 (back to Adam / "son of God").
- 1 Chronicles 1–9.
**Suggested edges.**
- `descends_from` : person → person
- `structures` : genealogy → book

### C4. `etymology` / `etiology` (treat as one type: `naming-etiology`)
**Definition.** A narrative explaining the origin of a name, place, or custom.
**Why current types miss it.** `wordplay` covers the sound-play; etiology covers the *narrative explanation* (why this stone is called Beth-el, why this practice exists).
**Examples.**
- Gen 28:19 (Bethel, "house of God").
- Gen 32:30 (Peniel, "face of God").
- Exod 17:7 (Massah and Meribah).
- Joshua 5:9 (Gilgal, "rolling away").
- 1 Samuel 7:12 (Ebenezer, "stone of help").
**Suggested edges.**
- `names` : etiology → place / person
- `explains` : etiology → festival / custom

### C5. `call-narrative`
**Definition.** A formal call/commissioning of a prophet or apostle, typically with: divine confrontation, commission, objection, reassurance, sign.
**Why current types miss it.** A genre with stable form (Habel's six-element pattern); currently invisible.
**Examples.**
- Moses (Exod 3:1–4:17).
- Gideon (Judg 6:11–24).
- Isaiah (Isa 6).
- Jeremiah (Jer 1:4–19).
- The disciples (Mark 1:16–20; John 1:35–51).
**Suggested edges.**
- `calls` : call-narrative → person (the called)
- `commissioned_by` : call-narrative → person (the caller, usually God)
- `parallels_form` : call-narrative → call-narrative

---

## 5. Group D — Hermeneutic Markers (5 types)

These are *relations between texts*, not texts themselves — but they merit unit-hood because they need to be retrievable as objects (e.g., "show me all typological fulfillments touching Passover"). Each unit-of-hermeneutic-relation pairs two or more texts.

### D1. `typological-fulfillment`
**Definition.** An OT *type* completed by an NT *antitype* (Adam/Christ, Passover/Eucharist, Jonah/Resurrection).
**Why current types miss it.** Currently approximated by `foreshadows` edge — but the *relation itself* deserves a unit so it can host commentary, dating, and provenance.
**Examples.**
- Adam → Christ (Rom 5:12–21).
- Passover lamb → Christ (1 Cor 5:7).
- Jonah's three days → resurrection (Matt 12:40).
- Bronze serpent → cross (John 3:14).
- Melchizedek → Christ (Heb 7).
**Suggested edges.**
- `type_of` : pericope → typological-fulfillment
- `antitype_of` : pericope → typological-fulfillment

### D2. `antitype`
**Definition.** The *fulfilled* member of a typological pair, taken as a unit in its own right (separate from the relation).
**Why current types miss it.** Distinct from D1 — D1 is the *relation*, D2 is the *NT pole*. Allows querying "all antitypes of Davidic kingship."
**Examples.**
- Christ as second Adam.
- The Church as new Israel.
- The heavenly Jerusalem (Rev 21) as antitype of earthly.
- Christ's body as new temple (John 2:21).
- Baptism as antitype of the Flood (1 Pet 3:20–21, where the term *antitypon* actually appears).
**Suggested edges.**
- `fulfills` : antitype → seed / pericope
- `recapitulates` : antitype → person (the OT figure)

### D3. `recapitulation`
**Definition.** A pattern where a later figure or event *re-runs* an earlier one, often correcting it (Israel's wilderness → Jesus' wilderness; Adam fails → Christ succeeds).
**Why current types miss it.** Stronger than `foreshadows` — it asserts a *re-performance*, with potential reversal.
**Examples.**
- Christ's 40 days in wilderness ↔ Israel's 40 years (Matt 4).
- Christ's temptation ↔ Adam's fall (Luke 4).
- Joshua entering Canaan ↔ Jesus (same name) leading into the kingdom.
- The new exodus (Isa 40–55) ↔ the first exodus.
- Pentecost ↔ Sinai (Acts 2 ↔ Exod 19).
**Suggested edges.**
- `recapitulates` : pericope → pericope
- `corrects` : recapitulation → pericope (when reversal is involved)

### D4. `reversal`
**Definition.** A narrative or rhetorical inversion: the high are brought low, the last are first, the curse becomes blessing.
**Why current types miss it.** Crucial for Lukan and prophetic theology; currently no way to surface that the Magnificat *is* a reversal text.
**Examples.**
- 1 Samuel 2 (Hannah's song) and Luke 1:46–55 (Magnificat).
- Joseph's brothers (Gen 50:20 — "you meant evil, God meant good").
- Haman / Mordecai (Esther 6–7).
- The cross as victory (Col 2:15).
- The last shall be first (Mark 10:31).
**Suggested edges.**
- `reverses` : reversal → motif / seed (the inverted theme)
- `mirrors_form_with` : reversal → reversal

### D5. `anti-parallel`
**Definition.** A pair of texts where the *form* matches but the *valence* is inverted (Babel/Pentecost; Eve/Mary; serpent on pole vs cross).
**Why current types miss it.** A `parallels` edge implies sameness; anti-parallel asserts *deliberate contrast in formal echo*.
**Examples.**
- Babel (Gen 11) ↔ Pentecost (Acts 2): one tongue confused; many tongues unified.
- Eve / Mary (the second-century *Eva–Ave* pair).
- Tree of knowledge (Gen 3) ↔ Tree of life / cross (Rev 22:2).
- Adam's sleep yields Eve from his side ↔ Christ's death yields the Church from his side.
- Saul's anointing (1 Sam 10) ↔ David's (1 Sam 16).
**Suggested edges.**
- `inverts` : pericope → pericope
- `formally_echoes` : anti-parallel → anti-parallel

---

## 6. Group E — Anti-Motif & Liturgical (5 types)

### E1. `anti-motif` (parent for false-prophet, idol, anti-temple, anti-messiah)
**Definition.** A *negative* counter-pattern that exists *as* the inversion of a positive motif. Distinct from "curse" (a speech-act) and from `motif` (which is value-neutral).
**Why current types miss it.** The current `motif` type treats "false prophet" as just another motif, losing the structural fact that it is *parasitic* on `prophet`.
**Examples.**
- False prophets (Deut 13; Jer 23; Matt 7:15; 2 Pet 2; Rev 16:13).
- Idolatry as anti-worship (golden calf; Baal; Jeroboam's calves).
- The anti-temple (Antiochus' abomination, 1 Macc 1:54; Mark 13:14).
- The anti-messiah / man of lawlessness (1 John 2:18; 2 Thess 2:3–10).
- The beast and false prophet (Rev 13).
**Suggested edges.**
- `inverts_motif` : anti-motif → motif
- `embodied_by` : anti-motif → person

### E2. `psalm-type` (genre tag for a psalm)
**Definition.** Form-critical category of a psalm: lament (individual / communal), hymn, thanksgiving, royal, wisdom, enthronement, songs-of-ascent.
**Why current types miss it.** No genre tag at all on psalms; retrieval can't ask "all enthronement psalms."
**Examples.**
- Royal: Ps 2, 18, 20, 21, 45, 72, 89, 110, 132.
- Enthronement: Ps 47, 93, 95–99.
- Songs of Ascent: Ps 120–134.
- Communal lament: Ps 44, 74, 79, 80, 137.
- Wisdom: Ps 1, 37, 49, 73, 112, 119.
**Suggested edges.**
- `genre_of` : psalm-type → pericope (psalm)
- `sibling_psalm` : psalm-type-grouped psalms.

### E3. `song`
**Definition.** A canonical *song* embedded in narrative — distinct from "psalm" (which is in the Psalter) and from "hymn" (NT term).
**Why current types miss it.** Songs are theological hinges in narrative (Song of the Sea, Song of Moses, Magnificat) and deserve a class.
**Examples.**
- Song of the Sea (Exod 15).
- Song of Moses (Deut 32).
- Song of Deborah (Judges 5).
- Song of Hannah (1 Sam 2).
- Magnificat, Benedictus, Nunc Dimittis (Luke 1–2).
**Suggested edges.**
- `sung_by` : song → person
- `theologizes` : song → pericope (the narrative event it comments on)

### E4. `prayer-formula`
**Definition.** Canonical fixed prayer or stable liturgical formula (Shema, Lord's Prayer, Aaronic blessing, Kaddish-like doxologies, maranatha).
**Why current types miss it.** A liturgical fixed-text needs its own class so worship-pattern queries are possible.
**Examples.**
- Shema (Deut 6:4–9).
- Aaronic blessing (Num 6:24–26).
- Lord's Prayer (Matt 6:9–13; Luke 11:2–4).
- Maranatha (1 Cor 16:22).
- "Amen" doxologies and the trishagion of Isa 6:3 / Rev 4:8.
**Suggested edges.**
- `recited_at` : prayer-formula → festival / liturgy
- `quoted_by` : pericope → prayer-formula

### E5. `hymn` (NT christological hymn or fragment)
**Definition.** An NT poetic-confessional fragment, usually marked by rhythm, hapax, and christological compression.
**Why current types miss it.** Distinct from `song` (narrative-embedded) and from `doxology` (short closing ascription); hymns are typically multi-strophic christological compressions.
**Examples.**
- Philippians 2:6–11 (kenosis hymn).
- Colossians 1:15–20 (cosmic-Christ hymn).
- 1 Timothy 3:16 (six-line credal hymn).
- John 1:1–18 (logos prologue, often analyzed as hymn).
- 1 Peter 3:18–22.
**Suggested edges.**
- `confesses` : hymn → title (the christological titles it deploys)
- `embedded_in` : hymn → pericope

---

## 7. Summary Table

| # | Slug | Group |
|---|------|-------|
| 1 | chiasm | Literary |
| 2 | inclusio | Literary |
| 3 | parallelism | Literary |
| 4 | hapax-legomenon | Literary |
| 5 | gematria | Literary |
| 6 | acrostic | Literary |
| 7 | wordplay | Literary |
| 8 | lament | Rhetorical |
| 9 | oath | Rhetorical |
| 10 | doxology | Rhetorical |
| 11 | beatitude | Rhetorical |
| 12 | woe | Rhetorical |
| 13 | blessing-form | Rhetorical |
| 14 | curse-form | Rhetorical |
| 15 | enigma | Rhetorical |
| 16 | dream | Narrative |
| 17 | vision | Narrative |
| 18 | genealogy | Narrative |
| 19 | naming-etiology | Narrative |
| 20 | call-narrative | Narrative |
| 21 | typological-fulfillment | Hermeneutic |
| 22 | antitype | Hermeneutic |
| 23 | recapitulation | Hermeneutic |
| 24 | reversal | Hermeneutic |
| 25 | anti-parallel | Hermeneutic |
| 26 | anti-motif | Anti / Liturgical |
| 27 | psalm-type | Liturgical |
| 28 | song | Liturgical |
| 29 | prayer-formula | Liturgical |
| 30 | hymn | Liturgical |

That is **30 proposed types**, taking the taxonomy from 16 → 46. The user's ask was "~24" — we recommend keeping all 30 as separable for retrieval, but if reduction is required the merge candidates are:
- `blessing-form` + `curse-form` → single `blessing-curse` (saves 1).
- `dream` + `vision` → single `vision` with subtype (saves 1; **not recommended** — dream/vision are formally distinct in Hebrew narrative).
- `antitype` collapses into `typological-fulfillment` (saves 1; **not recommended** — losing the asymmetric query "all antitypes of X").
- `song` + `hymn` → single `cantical` (saves 1).
- `beatitude` and `woe` could collapse but are *paired inverses* — keep both.

Minimum reduction reaches 26; aggressive reduction reaches 24.

---

## 8. Next Steps

1. **Review** this proposal — confirm/cut types, lock in slugs.
2. **Schema migration** — add a `subtype` column to `unit` for parallelism (synonymous/antithetic/etc.) and psalm-type genre, and extend `edge.kind` with the new edge slugs (`mirrors`, `brackets`, `inverts_motif`, `recapitulates`, `formally_echoes`, etc.).
3. **Seed content generation (pass 2)** — author 6–12 seed markdown files per accepted type. Suggested templates:
   - One H1 with the canonical example (e.g., `# Chiasm — Genesis 17`).
   - Verse range, key references, 200–400 words of exegesis, suggested edges in YAML front-matter.
4. **Backfill edges** — once content is embedded, run `cross_link.py` to populate the new edge kinds against existing pericope/seed nodes.
5. **Validation** — sample retrieval queries that *should* return the new types (e.g., "show me every reversal touching Mary" should now return Magnificat with `psalm-type`, `song`, and `reversal` tags simultaneously).

---

*End of proposal.*
