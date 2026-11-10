"""Tests for the shared Yomitan writer. Run: python -I -m unittest discover -s fumika_dict_common -t . -v"""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fumika_dict_common.yomitan import Meta, Tag, TermRow, content_names, read_term_rows, sc, write_dictionary

META = Meta(
    file_name="demo", title="Demo", revision="1", author="alrisa", attribution="CC BY 4.0", url="https://example.org",
    description="d",
)


class WriterTest(unittest.TestCase):
    def test_writes_zip_and_index_beside_it(self) -> None:
        rows = [TermRow("cat", "n", 0, [{"type": "structured-content", "content": sc("glosses", [], "ol")}], 1)]
        with tempfile.TemporaryDirectory() as tmp:
            zip_path, index_path, count = write_dictionary(Path(tmp), META, rows, [Tag("n", "partOfSpeech", "noun")])
            self.assertEqual(count, 1)
            with zipfile.ZipFile(zip_path) as z:
                self.assertEqual(sorted(z.namelist()), ["index.json", "tag_bank_1.json", "term_bank_1.json"])
                index = json.loads(z.read("index.json"))
                self.assertEqual(json.loads(z.read("tag_bank_1.json")), [["n", "partOfSpeech", 0, "noun", 0]])
            self.assertEqual(index["format"], 3)
            self.assertEqual(index["indexUrl"], "https://github.com/albertalrisa/fumika-dictionaries/releases/latest/download/demo.json")
            self.assertEqual(index["downloadUrl"], "https://github.com/albertalrisa/fumika-dictionaries/releases/latest/download/demo.zip")
            self.assertTrue(index["isUpdatable"])
            self.assertEqual(json.loads(index_path.read_text(encoding="utf-8")), index)
            self.assertEqual(read_term_rows(zip_path)[0][:3], ["cat", "", "n"])

    def test_banks_split_and_output_is_repeatable(self) -> None:
        rows = [TermRow(f"w{i}", "", 0, ["x"], i) for i in range(10_001)]
        with tempfile.TemporaryDirectory() as tmp:
            a, _, _ = write_dictionary(Path(tmp) / "a", META, rows, [])
            b, _, _ = write_dictionary(Path(tmp) / "b", META, rows, [])
            with zipfile.ZipFile(a) as z:
                self.assertIn("term_bank_2.json", z.namelist())
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_content_names(self) -> None:
        tree = [sc("a", [sc("b", "x", "span")]), {"tag": "li", "content": "plain"}]
        self.assertEqual(content_names(tree), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
