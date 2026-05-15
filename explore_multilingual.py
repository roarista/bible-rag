"""
Multilingual anchor-verse walk: Hebrew + Aramaic (BHSA) + Greek (N1904) + English (WEB).

Demonstrates that the four languages of the Bible RAG are all queryable
through one Python process, with full morphology where available.

Anchor verses:
  - Isaiah 53:5     → Hebrew (Suffering Servant — pierced for transgressions)
  - Daniel 2:4b     → Aramaic (where the Aramaic section begins)
  - John 19:34      → Greek (the spear thrust — fulfillment of Zech 12:10 + Ps 22)
  - Matthew 27:46   → Greek (Jesus quotes Psalm 22:1 from the cross)
  - Plus the English of each via bible-api.com (World English Bible, public domain)
"""

import urllib.request
import json
from tf.app import use


def english(reference: str) -> str:
    """Pull WEB (World English Bible, PD) verse text from bible-api.com."""
    url = f"https://bible-api.com/{urllib.parse.quote(reference)}?translation=web"
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
    return data["text"].strip().replace("\n", " ")


def banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


import urllib.parse  # noqa: E402


# -- Hebrew + Aramaic via BHSA --------------------------------------------
banner("LOADING BHSA (Hebrew + Aramaic)")
A_heb = use("ETCBC/bhsa", hoist=False, silent="deep")
Fh, Lh, Th = A_heb.api.F, A_heb.api.L, A_heb.api.T

# Isaiah 53:5 — Hebrew anchor
banner("ISAIAH 53:5  —  Hebrew")
v = Th.nodeFromSection(("Isaiah", 53, 5))
print(f"  Hebrew: {Th.text(v).strip()}")
print(f"  Language tag on words: {set(Fh.language.v(w) for w in Lh.d(v, otype='word'))}")
print(f"  English (WEB): {english('Isaiah 53:5')}")

# Daniel 2:4 — Aramaic anchor (Aramaic starts mid-verse with 'aramith')
banner("DANIEL 2:4b  —  Aramaic")
v = Th.nodeFromSection(("Daniel", 2, 4))
print(f"  Aramaic+Hebrew text: {Th.text(v).strip()}")
langs = {Fh.language.v(w) for w in Lh.d(v, otype="word")}
print(f"  Languages present in this verse: {langs}")
aramaic_words = [w for w in Lh.d(v, otype="word") if Fh.language.v(w) == "Aramaic"]
print(f"  Aramaic word count: {len(aramaic_words)}")
print(f"  First 5 Aramaic words with glosses:")
for w in aramaic_words[:5]:
    lex_node = Lh.u(w, otype="lex")
    gloss = Fh.gloss.v(lex_node[0]) if lex_node else ""
    print(f"    {Fh.g_word_utf8.v(w):>12}  lex={Fh.lex_utf8.v(w):<8}  gloss={gloss}")
print(f"  English (WEB): {english('Daniel 2:4')}")


# -- Greek NT via N1904 ---------------------------------------------------
banner("LOADING N1904 (Greek NT)")
A_grk = use("CenterBLC/N1904", hoist=False, silent="deep")
Fg, Lg, Tg = A_grk.api.F, A_grk.api.L, A_grk.api.T


def show_greek(book: str, ch: int, v: int) -> None:
    banner(f"{book} {ch}:{v}  —  Greek")
    verse_node = Tg.nodeFromSection((book, ch, v))
    print(f"  Greek: {Tg.text(verse_node).strip()}")
    print(f"  Word breakdown (first 8):")
    for w in Lg.d(verse_node, otype="word")[:8]:
        surface = Fg.unaccent.v(w) or ""
        lemma = Fg.lemma.v(w) or ""
        gloss = Fg.gloss_EN.v(w) if hasattr(Fg, "gloss_EN") else ""
        pos = Fg.sp.v(w) or ""
        print(f"    {surface:>15}  lemma={lemma:<14}  pos={pos:<6}  gloss={gloss}")
    print(f"  English (WEB): {english(f'{book} {ch}:{v}')}")


show_greek("Matthew", 27, 46)   # Eli Eli lama sabachthani — quoting Ps 22:1
show_greek("John", 19, 34)      # The spear thrust — pierced
show_greek("John", 19, 37)      # "They will look on him whom they pierced" — Zech 12:10

banner("DONE — Four languages, one process. All anchor verses accessible.")
print("""
What's queryable RIGHT NOW without any further work:

  • Every verse in the Hebrew OT (BHSA): morphology, lexeme, gloss, syntax
  • Every Aramaic verse in Daniel/Ezra (BHSA marks language='Aramaic')
  • Every verse in the Greek NT (N1904): morphology, lemma, gloss, syntax
  • Any verse in English (bible-api.com → World English Bible, fully PD)

What's NOT yet built (next milestones):

  • Verse-aligned join across Hebrew/Aramaic/Greek/English (need a unified verse-key)
  • Semantic embeddings at multiple scales (verses, pericopes, stories)
  • Cross-reference graph (Treasury of Scripture Knowledge)
  • Story/typology layer (see 06-Typology-Story-Layer.md)
  • Multi-agent contestation pipeline
""")
