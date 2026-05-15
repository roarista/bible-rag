"""
First contact with BHSA (Biblia Hebraica Stuttgartensia Amstelodamensis)
via Text-Fabric. Goal: confirm we can walk the 7-level hierarchy on a real
anchor verse — Isaiah 53:5.

BHSA levels available out of the box:
  book → chapter → verse → sentence → clause → phrase → subphrase → word
Plus per-word: lex (lexeme), morphology, gloss, semantic domain, part-of-speech.

This script:
  1. Loads BHSA (~700MB, auto-downloaded from ETCBC/bhsa on GitHub, cached at ~/text-fabric-data)
  2. Locates Isaiah 53:5
  3. Walks every level downward and prints what we get
  4. Demonstrates Hebrew-letter access (level 7 from our 7-level model)
"""

from tf.app import use

print("Loading BHSA — first run will download ~700MB and cache it. Be patient.\n")
A = use("ETCBC/bhsa", hoist=globals())

print("\n" + "=" * 70)
print("ANCHOR: Isaiah 53:5")
print("=" * 70)

verse_node = T.nodeFromSection(("Isaiah", 53, 5))
print(f"\nVerse node id: {verse_node}")
print(f"Plain text: {T.text(verse_node)}\n")

print("-" * 70)
print("LEVEL 1 — Book")
print("-" * 70)
book_node = L.u(verse_node, otype="book")[0]
print(f"  Book: {T.sectionFromNode(book_node)[0]}")
print(f"  Total chapters in book: {len(L.d(book_node, otype='chapter'))}")
print(f"  Total verses in book: {len(L.d(book_node, otype='verse'))}")
print(f"  Total words in book: {len(L.d(book_node, otype='word'))}")

print("\n" + "-" * 70)
print("LEVEL 2 — Chapter")
print("-" * 70)
chapter_node = L.u(verse_node, otype="chapter")[0]
print(f"  Chapter: Isaiah {T.sectionFromNode(chapter_node)[1]}")
print(f"  Verses in chapter: {len(L.d(chapter_node, otype='verse'))}")

print("\n" + "-" * 70)
print("LEVEL 3-4 — Sentence/Clause (structural units within verse)")
print("-" * 70)
for clause in L.d(verse_node, otype="clause"):
    print(f"  Clause {clause}: {T.text(clause).strip()}")

print("\n" + "-" * 70)
print("LEVEL 5 — Phrase")
print("-" * 70)
for phrase in L.d(verse_node, otype="phrase"):
    print(f"  Phrase {phrase}: {T.text(phrase).strip()}")

print("\n" + "-" * 70)
print("LEVEL 6 — Word (with morphology and gloss)")
print("-" * 70)
for word in L.d(verse_node, otype="word"):
    surface = F.g_word_utf8.v(word)
    lex = F.lex_utf8.v(word)
    pos = F.sp.v(word)
    gloss = F.gloss.v(L.u(word, otype="lex")[0]) if L.u(word, otype="lex") else ""
    print(f"  {surface:>15}  lex={lex:<10}  pos={pos:<6}  gloss={gloss}")

print("\n" + "-" * 70)
print("LEVEL 7 — Letters (character-level)")
print("-" * 70)
words_text = T.text(verse_node)
letters_only = [c for c in words_text if "֐" <= c <= "׿"]
print(f"  Total Hebrew letters in verse: {len(letters_only)}")
from collections import Counter
counts = Counter(letters_only)
print(f"  Letter frequency: {dict(counts.most_common())}")

print("\n" + "=" * 70)
print("SUCCESS — all 7 levels accessible. The 7-level model is real.")
print("=" * 70)
