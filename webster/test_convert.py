"""Tests for the Webster's 1913 converter: a small fixture, then known words checked against the real text.

Run: python -I -m unittest discover -s webster -t . -v
The real-source tests need sources/webster/pg29765.txt and are skipped without it.
"""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fumika_dict_common.yomitan import FUMIKA_WIKTIONARY_NAMES, content_names, read_term_rows
from webster import convert

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "sources" / "webster" / "pg29765.txt"

FIXTURE = """Title: Test

Release date: August 22, 2009 [eBook #29765]
                Most recently updated: July 6, 2025

*** START OF THE PROJECT GUTENBERG EBOOK TEST ***

BANK
Bank, n. Etym: [OE. banke; akin to E. bench, and prob. of Scand.
origin.; cf. Icel. bakki. See Bench.]

1. A mound, pile, or ridge of earth, raised above the surrounding
level; as, a bank of clouds.
They cast up a bank against the city. 2 Sam. xx. 15.

5. (Mining)
(a) The face of the coal at which miners are working.
(b) A deposit of ore or coal.

Note: Banks are many.

BANK
Bank, v. t. [imp. & p. p. Banked(p. pr. & vb. n. Banking.]

1. To raise a mound about; to embank.

2. (Law)

Defn: To bench.

ABATIS; ABATTIS
Ab"a*tis, n. Etym: [F.]

Defn: Trees laid side by side.

AEON
Æ"on, n. (Zoöl.)

Defn: An age.

BROKEN
Wrong"form, n.

Defn: Does not match.

EMPTY
Emp"ty, a.

*** END OF THE PROJECT GUTENBERG EBOOK TEST ***
"""


class FixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.entries, self.revision = convert.parse(FIXTURE)
        self.by_key = {(e.headword, e.pos): e for e in self.entries}

    def test_revision_is_the_gutenberg_update_date(self) -> None:
        self.assertEqual(self.revision, "2025-07-06")

    def test_headword_boundaries_and_failures(self) -> None:
        self.assertEqual([e.headword for e in self.entries], ["BANK", "BANK", "ABATIS; ABATTIS", "AEON", "BROKEN", "EMPTY"])
        failures = {e.headword: e.failure for e in self.entries if e.failure}
        self.assertIn("does not match the headword", failures["BROKEN"])
        self.assertIn("no sense with text", failures["EMPTY"])
        self.assertEqual(len(failures), 2)

    def test_numbered_senses_subsenses_and_labels(self) -> None:
        bank = self.by_key[("BANK", "n")]
        self.assertEqual(bank.pos, "n")
        self.assertTrue(bank.etymology.startswith("OE. banke"))
        self.assertEqual(bank.numbers, [1, 5])
        self.assertTrue(bank.senses[0].text.startswith("A mound, pile, or ridge of earth"))
        self.assertEqual(bank.senses[1].field, "Mining")
        self.assertEqual(bank.senses[1].subs, ["The face of the coal at which miners are working.", "A deposit of ore or coal."])
        self.assertEqual(bank.notes, [("Note", "Banks are many.")])

    def test_defn_fills_a_sense_header_and_pos_keeps_its_parts(self) -> None:
        verb = self.by_key[("BANK", "v. t")]
        self.assertEqual(verb.grammar, "imp. & p. p. Banked(p. pr. & vb. n. Banking.")
        self.assertEqual([(s.field, s.text) for s in verb.senses], [("", "To raise a mound about; to embank."), ("Law", "To bench.")])

    def test_variants_ligatures_and_entry_field(self) -> None:
        self.assertFalse(self.by_key[("ABATIS; ABATTIS", "n")].failure)
        aeon = self.by_key[("AEON", "n")]
        self.assertFalse(aeon.failure)
        self.assertEqual(aeon.entry_field, "Zoöl.")

    def test_rows_and_names(self) -> None:
        rows, tags = convert.build(self.entries)
        self.assertEqual([r.term for r in rows], ["bank", "bank", "abatis", "abattis", "aeon"])
        self.assertEqual({t.name: t.notes for t in tags}["v.t."], "transitive verb")
        self.assertIn("n.", {t.name for t in tags})
        names = set()
        for r in rows:
            names |= content_names(r.definitions)
        self.assertLessEqual(names, FUMIKA_WIKTIONARY_NAMES)
        self.assertIn("glosses", names)

    def test_report_counts(self) -> None:
        text = convert.report(self.entries)
        self.assertIn("headwords found:   6", text)
        self.assertIn("failed (left out): 2", text)

    def test_zip_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "w.txt"
            src.write_text(FIXTURE, encoding="utf-8", newline="")
            zip_path, index_path, count, _ = convert.convert(src, Path(tmp) / "out")
            self.assertEqual(count, 5)
            with zipfile.ZipFile(zip_path) as z:
                index = json.loads(z.read("index.json"))
            self.assertEqual(index["format"], 3)
            # the converter's own release follows the source's date, so a fixed conversion reaches installed copies
            self.assertEqual(index["revision"], "2025-07-06.2")
            self.assertEqual(index["downloadUrl"], "https://github.com/albertalrisa/fumika-dictionaries/releases/latest/download/webster1913.zip")
            self.assertTrue((Path(tmp) / "out" / "webster1913-parse-report.txt").exists())


@unittest.skipUnless(SOURCE.exists(), "the Gutenberg text is not downloaded")
class RealSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        cls.raw_lines = text.replace("\r\n", "\n").split("\n")
        cls.entries, _ = convert.parse(text)
        cls.rows, _ = convert.build(cls.entries)

    def raw_headword_count(self, word: str) -> int:
        return sum(1 for i, l in enumerate(self.raw_lines) if l == word and i > 0 and self.raw_lines[i - 1] == "")

    def test_every_headword_line_is_an_entry_clean_or_reported(self) -> None:
        for word in ("BANK", "RUN", "SET"):
            with self.subTest(word=word):
                mine = [e for e in self.entries if e.headword == word]
                self.assertEqual(len(mine), self.raw_headword_count(word))
                self.assertGreaterEqual(len([e for e in mine if not e.failure]), 1)

    def test_bank_first_noun_matches_the_text(self) -> None:
        bank = next(e for e in self.entries if e.headword == "BANK" and e.pos == "n")
        self.assertEqual(bank.numbers[:5], [1, 2, 3, 4, 5])
        self.assertTrue(bank.senses[0].text.startswith("A mound, pile, or ridge of earth, raised above the surrounding level"))
        self.assertEqual(bank.senses[4].field, "Mining")
        self.assertEqual(len(bank.senses[4].subs), 3)

    def test_run_and_set_have_verb_and_noun_senses(self) -> None:
        for word in ("RUN", "SET"):
            with self.subTest(word=word):
                poses = {e.pos for e in self.entries if e.headword == word and not e.failure}
                self.assertIn("n", poses)
                self.assertTrue(poses & {"v. i", "v. t"})
                self.assertTrue(any(len(e.senses) >= 5 for e in self.entries if e.headword == word and not e.failure))

    def test_rows_are_looked_up_by_lower_case_term(self) -> None:
        terms = {r.term for r in self.rows}
        self.assertTrue({"bank", "run", "set"} <= terms)

    def test_most_entries_parse_cleanly(self) -> None:
        clean = sum(1 for e in self.entries if not e.failure)
        self.assertGreater(clean / len(self.entries), 0.98)
        self.assertGreater(len(self.entries), 100_000)

    def test_zip_round_trip_has_only_styled_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path, _, count, _ = convert.convert(SOURCE, Path(tmp))
            rows = read_term_rows(zip_path)
            self.assertEqual(len(rows), count)
            names = set()
            for r in rows:
                names |= content_names(r[5])
            self.assertLessEqual(names, FUMIKA_WIKTIONARY_NAMES)


if __name__ == "__main__":
    unittest.main()
