"""Tests for the WordNet converter: a small fixture, then known words checked against the real source.

Run: python -I -m unittest discover -s wordnet -t . -v
The real-source tests need sources/wordnet/english-wordnet-2025.xml.gz and are skipped without it.
"""
from __future__ import annotations

import gzip
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from fumika_dict_common.yomitan import FUMIKA_WIKTIONARY_NAMES, content_names, read_term_rows
from wordnet import convert

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "sources" / "wordnet" / "english-wordnet-2025.xml.gz"

FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource>
  <Lexicon id="oewn" label="Open English Wordnet" language="en" version="2025">
    <LexicalEntry id="oewn-cat-n"><Lemma writtenForm="cat" partOfSpeech="n"/>
      <Sense id="oewn-cat__1" synset="oewn-1-n"/><Sense id="oewn-cat__2" synset="oewn-2-n"/></LexicalEntry>
    <LexicalEntry id="oewn-true_cat-n"><Lemma writtenForm="true cat" partOfSpeech="n"/>
      <Sense id="oewn-true_cat__1" synset="oewn-1-n"/></LexicalEntry>
    <LexicalEntry id="oewn-cat-v"><Lemma writtenForm="cat" partOfSpeech="v"/>
      <Sense id="oewn-cat__v1" synset="oewn-3-v"/></LexicalEntry>
    <LexicalEntry id="oewn-odd-s"><Lemma writtenForm="odd" partOfSpeech="s"/>
      <Sense id="oewn-odd__1" synset="oewn-4-s"/></LexicalEntry>
    <Synset id="oewn-1-n" members="oewn-cat-n oewn-true_cat-n" partOfSpeech="n">
      <Definition>a small furry animal</Definition><Example>the cat sat</Example><Example>two cats</Example></Synset>
    <Synset id="oewn-2-n" members="oewn-cat-n" partOfSpeech="n"><Definition>a whip</Definition></Synset>
    <Synset id="oewn-3-v" members="oewn-cat-v" partOfSpeech="v"><Definition>to vomit</Definition></Synset>
    <Synset id="oewn-4-s" members="oewn-odd-s" partOfSpeech="s"><Definition>strange</Definition></Synset>
  </Lexicon>
</LexicalResource>
"""


def glosses(row: list) -> list[dict]:
    content = row[5][0]["content"]
    assert content[0]["data"] == {"content": "glosses"}
    return content[0]["content"]


def gloss_text(item: dict) -> str:
    return item["content"]["content"][0]


class FixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = convert.build_rows(convert.read(io.BytesIO(FIXTURE)))
        self.by_key = {(r.term, r.definition_tags): r.row() for r in self.rows}

    def test_one_row_per_headword_and_part_of_speech(self) -> None:
        self.assertEqual(sorted(self.by_key), [("cat", "n"), ("cat", "v"), ("odd", "adj"), ("true cat", "n")])

    def test_numbered_glosses_with_examples_folded_under_them(self) -> None:
        items = glosses(self.by_key[("cat", "n")])
        self.assertEqual([gloss_text(i) for i in items], ["a small furry animal", "a whip"])
        details = items[0]["content"]["content"][1]
        self.assertEqual(details["tag"], "details")
        self.assertEqual(details["data"], {"content": "details-entry-examples"})
        self.assertEqual(details["content"][0]["content"], "2 examples")
        self.assertEqual(len(items[1]["content"]["content"]), 1)  # no examples, no details

    def test_synonyms_are_the_other_members_as_lookup_links(self) -> None:
        related = self.by_key[("cat", "n")][5][0]["content"][1]
        self.assertEqual(related["data"], {"content": "related-words"})
        items = related["content"]["content"]["content"]
        self.assertEqual(items[0]["data"], {"content": "synonym-item"})
        self.assertEqual(items[0]["content"], {"tag": "a", "href": "?query=true%20cat", "content": "true cat"})

    def test_only_names_fumika_styles(self) -> None:
        names: set[str] = set()
        for row in self.rows:
            names |= content_names(row.definitions)
        self.assertLessEqual(names, FUMIKA_WIKTIONARY_NAMES)
        self.assertTrue({"glosses", "related-words", "synonyms", "backlink", "details-entry-examples"} <= names)

    def test_no_synonyms_block_when_none(self) -> None:
        names = [n.get("data", {}).get("content") for n in self.by_key[("cat", "v")][5][0]["content"]]
        self.assertEqual(names, ["glosses", "backlink"])

    def test_zip_has_index_tags_and_banks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "wn.xml.gz"
            raw.write_bytes(gzip.compress(FIXTURE))
            zip_path, index_path, count = convert.convert(raw, Path(tmp) / "out")
            self.assertEqual(count, 4)
            with zipfile.ZipFile(zip_path) as z:
                self.assertEqual(sorted(z.namelist()), ["index.json", "tag_bank_1.json", "term_bank_1.json"])
                index = json.loads(z.read("index.json"))
            self.assertEqual(index["format"], 3)
            self.assertEqual(index["revision"], "2025")
            self.assertTrue(index["isUpdatable"])
            self.assertEqual(index["downloadUrl"], "https://github.com/albertalrisa/fumika-dictionaries/releases/latest/download/oewn.zip")
            self.assertEqual(json.loads(index_path.read_text(encoding="utf-8")), index)


@unittest.skipUnless(SOURCE.exists(), "the OEWN source is not downloaded")
class RealSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        zip_path, _, cls.count = convert.convert(SOURCE, Path(cls.tmp.name))
        cls.rows = {}
        for r in read_term_rows(zip_path):
            cls.rows[(r[0], r[2])] = r
        with gzip.open(SOURCE, "rb") as f:
            cls.tree = ET.parse(f).getroot()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def source_glosses(self, word: str, pos: str) -> list[str]:
        """The definitions of every synset of the word's entries of that part of speech, read straight from the XML."""
        synset_ids: list[str] = []
        for entry in self.tree.iter("LexicalEntry"):
            lemma = entry.find("Lemma")
            if lemma.get("writtenForm") == word and lemma.get("partOfSpeech") in pos:
                synset_ids += [s.get("synset") for s in entry.findall("Sense")]
        texts = {s.get("id"): s.find("Definition").text for s in self.tree.iter("Synset")}
        return [texts[i] for i in dict.fromkeys(synset_ids)]

    def test_run_bank_set_senses_match_the_source(self) -> None:
        for word, tag, pos in [("run", "n", "n"), ("run", "v", "v"), ("bank", "n", "n"), ("bank", "v", "v"),
                               ("set", "n", "n"), ("set", "v", "v"), ("set", "adj", "as")]:
            with self.subTest(word=word, pos=tag):
                got = [gloss_text(i) for i in glosses(self.rows[(word, tag)])]
                self.assertEqual(got, self.source_glosses(word, pos))

    def test_known_values(self) -> None:
        bank = glosses(self.rows[("bank", "n")])
        self.assertEqual(len(bank), 10)
        self.assertEqual(gloss_text(bank[0]), "sloping land (especially the slope beside a body of water)")
        self.assertEqual(bank[0]["content"]["content"][1]["content"][0]["content"], "2 examples")
        self.assertEqual(len(glosses(self.rows[("run", "v")])), 41)
        self.assertEqual(self.rows[("bank", "n")][2], "n")

    def test_synonyms_of_a_known_synset(self) -> None:
        bank_synonyms = self.rows[("bank", "n")][5][0]["content"][1]["content"]["content"]["content"]
        words = [i["content"]["content"] for i in bank_synonyms]
        self.assertIn("cant", words)
        self.assertIn("camber", words)
        self.assertNotIn("bank", words)

    def test_size(self) -> None:
        self.assertGreater(self.count, 130_000)


if __name__ == "__main__":
    unittest.main()
