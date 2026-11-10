"""Writes a Yomitan dictionary (format 3): a zip with index.json, term banks and a tag bank, plus the index beside it."""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

RELEASE_BASE = "https://github.com/albertalrisa/fumika-dictionaries/releases/latest/download"
ROWS_PER_BANK = 10_000
FIXED_ZIP_TIME = (2025, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class Tag:
    name: str
    category: str
    notes: str
    order: float = 0
    score: float = 0

    def row(self) -> list:
        return [self.name, self.category, self.order, self.notes, self.score]


@dataclass(frozen=True)
class TermRow:
    term: str
    definition_tags: str
    score: float
    definitions: list
    sequence: int
    term_tags: str = ""
    reading: str = ""
    rules: str = ""

    def row(self) -> list:
        return [
            self.term, self.reading, self.definition_tags, self.rules, self.score,
            self.definitions, self.sequence, self.term_tags,
        ]


@dataclass(frozen=True)
class Meta:
    file_name: str  # the release file name without extension, e.g. "oewn"
    title: str
    revision: str
    author: str
    attribution: str
    url: str
    description: str
    source_language: str = "en"
    target_language: str = "en"
    extra: dict = field(default_factory=dict)

    def index(self) -> dict:
        index = {
            "title": self.title,
            "revision": self.revision,
            "format": 3,
            "sequenced": True,
            "author": self.author,
            "description": self.description,
            "attribution": self.attribution,
            "url": self.url,
            "sourceLanguage": self.source_language,
            "targetLanguage": self.target_language,
            "isUpdatable": True,
            "indexUrl": f"{RELEASE_BASE}/{self.file_name}.json",
            "downloadUrl": f"{RELEASE_BASE}/{self.file_name}.zip",
        }
        index.update(self.extra)
        return index


def dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_dictionary(out_dir: Path, meta: Meta, rows: Iterable[TermRow], tags: Sequence[Tag]) -> tuple[Path, Path, int]:
    """Writes `<file_name>.zip` and `<file_name>.json` into out_dir; returns both paths and the row count."""
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{meta.file_name}.zip"
    index_path = out_dir / f"{meta.file_name}.json"
    index_text = json.dumps(meta.index(), ensure_ascii=False, indent=2) + "\n"

    def add(archive: zipfile.ZipFile, name: str, text: str) -> None:
        info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, text.encode("utf-8"))

    count = 0
    with zipfile.ZipFile(zip_path, "w") as archive:
        add(archive, "index.json", index_text)
        add(archive, "tag_bank_1.json", dump([t.row() for t in tags]))
        bank: list = []
        number = 1

        def flush() -> None:
            nonlocal bank, number
            if bank:
                add(archive, f"term_bank_{number}.json", dump(bank))
                number += 1
                bank = []

        for row in rows:
            bank.append(row.row())
            count += 1
            if len(bank) >= ROWS_PER_BANK:
                flush()
        flush()
    with index_path.open("w", encoding="utf-8", newline="") as f:
        f.write(index_text)
    return zip_path, index_path, count


def read_term_rows(zip_path: Path) -> list[list]:
    """Every term row of a written zip (for tests and checks)."""
    rows: list[list] = []
    with zipfile.ZipFile(zip_path) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith("term_bank_"):
                rows.extend(json.loads(archive.read(name).decode("utf-8")))
    return rows


def sc(name: str, content: object, tag: str = "div") -> dict:
    """A structured-content node named the way Fumika's stylesheet expects (`data-sc-content`)."""
    return {"tag": tag, "data": {"content": name}, "content": content}


# The `data.content` names Fumika's stylesheet lays out for the Wiktionary dictionaries
# (src/components/reader/lookup/structuredContent.css in the Fumika repository). Entries should use only these.
FUMIKA_WIKTIONARY_NAMES = frozenset({
    "glosses", "tags", "tag", "preamble", "summary-entry", "Grammar-content", "Etymology-content",
    "details-entry-examples", "bold-text", "extra-info", "example-sentence", "example-sentence-a",
    "example-sentence-c", "related-words", "synonyms", "antonyms", "synonyms-list", "antonyms-list",
    "synonym-item", "antonym-item", "backlink",
})


def content_names(node: object) -> set[str]:
    """Every `data.content` name used in a structured-content tree."""
    names: set[str] = set()
    if isinstance(node, list):
        for child in node:
            names |= content_names(child)
    elif isinstance(node, dict):
        data = node.get("data")
        if isinstance(data, dict) and "content" in data:
            names.add(data["content"])
        names |= content_names(node.get("content"))
    return names
