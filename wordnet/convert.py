"""Open English WordNet (WN-LMF XML, gzipped) to a Yomitan dictionary.

One term row per headword and part of speech; its definition is a numbered list of glosses (each with its examples
folded under it), the synonyms from all its senses, and a link back to the source. The structured-content names are
the ones Fumika's stylesheet already lays out for the Wiktionary dictionaries.

Run: python -I wordnet/convert.py <english-wordnet-xml.gz> <out_dir>
"""
from __future__ import annotations

import gzip
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fumika_dict_common.yomitan import Meta, Tag, TermRow, sc, write_dictionary  # noqa: E402

FILE_NAME = "oewn"
SOURCE_URL = "https://github.com/globalwordnet/english-wordnet"
LEMMA_URL = "https://en-word.net/lemma/"
MAX_SYNONYMS = 30

# WN-LMF part of speech -> (tag name, tag notes, rank). Adjective satellites read as adjectives.
POS = {
    "n": ("n", "noun", 4),
    "v": ("v", "verb", 3),
    "a": ("adj", "adjective", 2),
    "s": ("adj", "adjective", 2),
    "r": ("adv", "adverb", 1),
}
TAGS = [
    Tag("n", "partOfSpeech", "noun", 0),
    Tag("v", "partOfSpeech", "verb", 1),
    Tag("adj", "partOfSpeech", "adjective", 2),
    Tag("adv", "partOfSpeech", "adverb", 3),
]


def ref(word: str) -> dict:
    return {"tag": "a", "href": f"?query={quote(word)}", "content": word}


def gloss_item(definition: str, examples: list[str]) -> dict:
    content: list = [definition]
    if examples:
        label = "1 example" if len(examples) == 1 else f"{len(examples)} examples"
        content.append(sc("details-entry-examples", [
            sc("summary-entry", label, "summary"),
            *[sc("extra-info", sc("example-sentence", sc("example-sentence-a", e))) for e in examples],
        ], "details"))
    return {"tag": "li", "content": {"tag": "div", "content": content}}


def synonyms_block(words: list[str]) -> dict:
    items = [{"tag": "li", "data": {"content": "synonym-item"}, "content": ref(w)} for w in words]
    return sc("related-words", sc("synonyms", {"tag": "ul", "data": {"content": "synonyms-list"}, "content": items}))


def backlink(word: str) -> dict:
    return sc("backlink", [
        "Open English WordNet, CC BY 4.0. ",
        {"tag": "a", "href": LEMMA_URL + quote(word), "content": "en-word.net"},
    ])


class Wordnet:
    """What the file holds, read in one pass: lemmas by entry id, synsets by id, entries in file order."""

    def __init__(self) -> None:
        self.version = ""
        self.lemma_of: dict[str, str] = {}
        self.entries: list[tuple[str, str, list[str]]] = []  # (word, pos, [synset ids in sense order])
        self.synsets: dict[str, tuple[str, list[str], list[str]]] = {}  # id -> (definition, examples, member entry ids)


def read(source: BinaryIO) -> Wordnet:
    wn = Wordnet()
    for _, el in ET.iterparse(source, events=("end",)):
        tag = el.tag
        if tag == "LexicalEntry":
            lemma = el.find("Lemma")
            if lemma is not None:
                word = lemma.get("writtenForm", "")
                wn.lemma_of[el.get("id", "")] = word
                synsets = [s.get("synset", "") for s in el.findall("Sense")]
                wn.entries.append((word, lemma.get("partOfSpeech", ""), synsets))
            el.clear()
        elif tag == "Synset":
            definitions = [(d.text or "").strip() for d in el.findall("Definition")]
            examples = [(e.text or "").strip() for e in el.findall("Example")]
            wn.synsets[el.get("id", "")] = (
                "; ".join(d for d in definitions if d),
                [e for e in examples if e],
                (el.get("members") or "").split(),
            )
            el.clear()
        elif tag == "Lexicon":
            wn.version = el.get("version", "")
    return wn


def build_rows(wn: Wordnet) -> list[TermRow]:
    """Entries sharing a headword and part of speech merge; synsets are listed once, in sense order."""
    merged: dict[tuple[str, str], list[str]] = defaultdict(list)
    for word, pos, synset_ids in wn.entries:
        if pos not in POS:
            continue
        group = merged[(word, POS[pos][0])]
        group.extend(s for s in synset_ids if s not in group)
    rows: list[TermRow] = []
    tag_rank = {POS[p][0]: POS[p][2] for p in POS}
    for sequence, ((word, pos), synset_ids) in enumerate(merged.items(), start=1):
        items: list[dict] = []
        synonyms: list[str] = []
        for synset_id in synset_ids:
            if synset_id not in wn.synsets:
                continue
            definition, examples, members = wn.synsets[synset_id]
            if not definition:
                continue
            items.append(gloss_item(definition, examples))
            for member in members:
                other = wn.lemma_of.get(member)
                if other and other != word and other not in synonyms:
                    synonyms.append(other)
        if not items:
            continue
        content: list = [sc("glosses", items, "ol")]
        if synonyms:
            content.append(synonyms_block(synonyms[:MAX_SYNONYMS]))
        content.append(backlink(word))
        rows.append(TermRow(
            term=word, definition_tags=pos, score=tag_rank[pos],
            definitions=[{"type": "structured-content", "content": content}], sequence=sequence,
        ))
    return rows


def convert(source_path: Path, out_dir: Path) -> tuple[Path, Path, int]:
    with gzip.open(source_path, "rb") as f:
        wn = read(f)
    rows = build_rows(wn)
    meta = Meta(
        file_name=FILE_NAME,
        title="Open English WordNet",
        revision=wn.version or "unknown",
        author="alrisa (conversion); Open English WordNet contributors (data)",
        attribution=(
            f"Open English WordNet {wn.version}, https://en-word.net, licensed CC BY 4.0 "
            "(https://creativecommons.org/licenses/by/4.0/). Converted to Yomitan format by fumika-dictionaries."
        ),
        url=SOURCE_URL,
        description="English to English: senses with glosses, examples and synonyms, from Open English WordNet (CC BY 4.0).",
    )
    return write_dictionary(out_dir, meta, rows, TAGS)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    zip_path, index_path, count = convert(Path(argv[1]), Path(argv[2]))
    print(f"{count} entries -> {zip_path} ({zip_path.stat().st_size} bytes), {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
