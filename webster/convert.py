"""Webster's Revised Unabridged Dictionary (1913, Project Gutenberg #29765) to a Yomitan dictionary.

The text is irregular, so the converter is strict: an entry that does not parse cleanly is left out and listed in the
parse report with the reason, never repaired by guesswork. An entry parses cleanly when

  * its headword line (all capitals) is followed by a headline whose form is that headword, and
  * its body gives at least one sense with text (a numbered sense, a `Defn:` paragraph).

Paragraphs the parser does not recognise stay in the entry as plain notes and are counted as warnings.

Run: python -I webster/convert.py <pg29765.txt> <out_dir>
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field as dc_field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fumika_dict_common.yomitan import Meta, Tag, TermRow, sc, write_dictionary  # noqa: E402

FILE_NAME = "webster1913"
GUTENBERG_URL = "https://www.gutenberg.org/ebooks/29765"
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
     "November", "December"], start=1)}

HEADWORD = re.compile(r"[A-Z][A-Z0-9' \-.À-ſ,;()&*\"]*")
NUMBERED = re.compile(r"^(\d+)\.(?:\s+(.*)|$)")
SUB_ITEM = re.compile(r"^\(([a-z])\)\s+(.*)")
FIELD = re.compile(r"^\(([A-Z][^()]{0,28})\)\s*(.*)$")
POS = re.compile(r"^[,.]?\s*((?:[a-z]{1,6}\.\s*(?:&\s*)?)+)")
OTHER_FORM = re.compile(r"^,\s*[^,\[(.\s][^,\[(.]*(?=,)")
FORM_END = re.compile(r"(?:,\s|\.\s*$|\.?\s+(?=(?:n|a|v|adv|prep|conj|interj|pron|p|imp|pl|obs|prefix|vb)\.\s*(?:[a-z]{1,6}\.\s*)*(?:$|\[|Etym:|\())|\s*\[|\s+Etym:|\s*\(|\s*$)")

# Raised whenever a change to this converter alters its output, so installed copies are offered the new one.
CONVERTER_RELEASE = 2

POS_NOTES = {
    "n": "noun", "a": "adjective", "v. t": "transitive verb", "v. i": "intransitive verb", "v": "verb",
    "adv": "adverb", "n. pl": "plural noun", "n. sing": "singular noun", "p. p": "past participle",
    "p. a": "participial adjective", "p. pr": "present participle", "imp": "imperfect", "interj": "interjection",
    "prep": "preposition", "pron": "pronoun", "conj": "conjunction", "prefix": "prefix", "pl": "plural",
}


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normal(form: str) -> str:
    """Letters and digits only, accents folded, lower case: the common ground of a headword and a syllabled form."""
    ligatures = {"æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe"}
    decomposed = unicodedata.normalize("NFKD", "".join(ligatures.get(ch, ch) for ch in form))
    return "".join(c for c in decomposed if c.isalnum() and not unicodedata.combining(c)).lower()


@dataclass
class Sense:
    field: str = ""
    text: str = ""
    subs: list[str] = dc_field(default_factory=list)
    more: list[str] = dc_field(default_factory=list)  # further paragraphs of the same sense


@dataclass
class Entry:
    line: int
    headword: str
    pos: str = ""
    grammar: str = ""
    etymology: str = ""
    entry_field: str = ""
    senses: list[Sense] = dc_field(default_factory=list)
    notes: list[tuple[str, str]] = dc_field(default_factory=list)
    stray: list[str] = dc_field(default_factory=list)
    numbers: list[int] = dc_field(default_factory=list)
    failure: str = ""


def gutenberg_body(text: str) -> tuple[list[str], str, int]:
    """The lines between the start and end markers, the revision (ISO date of the latest Gutenberg update) and the
    number of lines before the body."""
    lines = text.replace("\r\n", "\n").split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("*** START OF"))
    end = next(i for i, l in enumerate(lines) if l.startswith("*** END OF"))
    revision = "unknown"
    for l in lines[:start]:
        m = re.match(r"\s*Most recently updated:\s*(\w+) (\d+), (\d{4})", l) or re.match(r"Release date:\s*(\w+) (\d+), (\d{4})", l)
        if m and m.group(1) in MONTHS and "Most" in l:
            revision = f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    return lines[start + 1:end], revision, start + 1


def split_blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    """(line number, lines) per entry: from a headword line (capitals, after a blank line) to the next one."""
    starts = [
        i for i, l in enumerate(lines)
        if l and i > 0 and lines[i - 1] == "" and HEADWORD.fullmatch(l) and i + 1 < len(lines) and lines[i + 1] != ""
    ]
    return [(s + 1, lines[s:e]) for s, e in zip(starts, starts[1:] + [len(lines)])]


def brackets(text: str) -> list[tuple[int, int]]:
    """Top-level [...] spans (start, end exclusive); an unclosed one runs to the end of the text."""
    spans, depth, begin = [], 0, 0
    for i, c in enumerate(text):
        if c == "[":
            if depth == 0:
                begin = i
            depth += 1
        elif c == "]" and depth > 0:
            depth -= 1
            if depth == 0:
                spans.append((begin, i + 1))
    if depth > 0:
        spans.append((begin, len(text)))
    return spans


def headline_length(lines: list[str]) -> int:
    """How many of the lines (after the headword) form the headline: until its brackets close or a blank line."""
    depth = 0
    for n, line in enumerate(lines, start=1):
        if line.strip() == "":
            return n - 1
        depth += line.count("[") - line.count("]")
        if depth <= 0:
            return n
    return len(lines)


def parse_headline(entry: Entry, headline: str) -> None:
    m = FORM_END.search(headline)
    form = headline[: m.start()] if m else headline
    first_form = normal(form.split(" or ")[0])
    if first_form not in {normal(v) for v in entry.headword.split(";")}:
        entry.failure = f"headline form {squash(form)!r} does not match the headword"
        return
    rest = headline[m.start():] if m else ""
    # further spellings of the headword come before the part of speech: "Banc, Ban"cus, Bank, n."
    while not POS.match(rest) and (other := OTHER_FORM.match(rest)):
        rest = rest[other.end():]
    pos = POS.match(rest)
    if pos:
        entry.pos = squash(pos.group(1)).rstrip(".").replace("v.t", "v. t").replace("v.i", "v. i").replace("p.p", "p. p")
        entry.pos = re.sub(r"\.(?=\S)", ". ", entry.pos).strip()
        rest = rest[pos.end():]
    pieces: list[str] = []
    cursor = 0
    for begin, end in brackets(rest):
        pieces.append(rest[cursor:begin])
        inner = rest[begin + 1:end - 1 if rest[end - 1] == "]" else end]
        if re.search(r"Etym:\s*$", rest[:begin]):
            entry.etymology = squash(inner)
            pieces[-1] = re.sub(r"Etym:\s*$", "", pieces[-1])
        else:
            entry.grammar = squash(inner)
        cursor = end
    pieces.append(rest[cursor:])
    leftover = squash(" ".join(pieces).replace("Etym:", ""))
    f = FIELD.match(leftover)
    if f and not f.group(2):
        entry.entry_field = f.group(1)
    elif leftover not in ("", "."):
        entry.grammar = squash(f"{entry.grammar} {leftover}")


def split_sense_start(text: str, sense: Sense) -> None:
    """A sense's first text: an optional (Field) label and the rest, with `Etym: [...]` folded into brackets."""
    text = squash(text)
    for begin, end in reversed(brackets(text)):
        if re.search(r"Etym:\s*$", text[:begin]):
            text = re.sub(r"Etym:\s*$", "", text[:begin]).rstrip() + " " + text[begin:end] + " " + text[end:]
    text = squash(text.replace("Etym:", ""))
    f = FIELD.match(text)
    if f:
        sense.field, text = f.group(1), f.group(2)
    sense.text = squash(text)


def parse_paragraph_into_sense(lines: list[str], sense: Sense, first_text: str) -> None:
    """Fills a sense from a paragraph whose first line has been reduced to `first_text`."""
    main = [first_text]
    subs: list[list[str]] = []
    for line in lines[1:]:
        m = SUB_ITEM.match(line)
        if m:
            subs.append([m.group(2)])
        elif subs:
            subs[-1].append(line)
        else:
            main.append(line)
    split_sense_start(" ".join(main), sense)
    sense.subs.extend(squash(" ".join(s)) for s in subs)


def parse_body(entry: Entry, paragraphs: list[list[str]]) -> None:
    current: Sense | None = None
    for lines in paragraphs:
        first = lines[0]
        numbered = NUMBERED.match(first)
        if numbered:
            current = Sense()
            entry.senses.append(current)
            entry.numbers.append(int(numbered.group(1)))
            parse_paragraph_into_sense(lines, current, numbered.group(2) or "")
        elif first.startswith("Defn:"):
            text = first[len("Defn:"):].strip()
            if current is not None and not current.text and not current.subs:
                parse_paragraph_into_sense(lines, current, text)
            elif current is not None:
                current.more.append(squash(" ".join([text] + lines[1:])))
            else:
                current = Sense()
                entry.senses.append(current)
                parse_paragraph_into_sense(lines, current, text)
        elif first.startswith("Note:"):
            entry.notes.append(("Note", squash(" ".join([first[5:]] + lines[1:]))))
        elif first.startswith("Syn."):
            entry.notes.append(("Syn.", squash(" ".join([first[4:]] + lines[1:]))))
        elif first.lstrip().startswith("--"):
            entry.notes.append(("", squash(" ".join(lines))))
        elif SUB_ITEM.match(first):
            if current is None:
                current = Sense()
                entry.senses.append(current)
            for line in lines:
                m = SUB_ITEM.match(line)
                if m:
                    current.subs.append(m.group(2))
                elif current.subs:
                    current.subs[-1] = squash(current.subs[-1] + " " + line)
        else:
            text = squash(" ".join(lines))
            label = FIELD.match(text)
            if label and not label.group(2):
                if current is None:
                    entry.entry_field = entry.entry_field or label.group(1)
                else:
                    current.field = current.field or label.group(1)
            elif re.fullmatch(r"(?:Etym:\s*)?\[.*\]\.?", text):
                inner = re.sub(r"^(?:Etym:\s*)?\[|\]\.?$", "", text)
                if current is None:
                    entry.etymology = entry.etymology or inner
                else:
                    current.more.append(f"[{inner}]")
            else:
                entry.stray.append(text)


def parse_entry(line: int, block: list[str]) -> Entry:
    entry = Entry(line=line, headword=block[0])
    rest = block[1:]
    count = headline_length(rest)
    parse_headline(entry, " ".join(rest[:count]))
    if entry.failure:
        return entry
    paragraphs: list[list[str]] = []
    pending: list[str] = []
    for l in rest[count:]:
        if l.strip() == "":
            if pending:
                paragraphs.append(pending)
                pending = []
        else:
            pending.append(l)
    if pending:
        paragraphs.append(pending)
    parse_body(entry, paragraphs)
    if not any(s.text or s.subs or s.more for s in entry.senses):
        entry.failure = "no sense with text (no numbered sense or Defn: paragraph)"
    return entry


def parse(text: str) -> tuple[list[Entry], str]:
    lines, revision, offset = gutenberg_body(text)
    return [parse_entry(n + offset, b) for n, b in split_blocks(lines)], revision


def numbering_irregular(entry: Entry) -> bool:
    expected = list(range(1, len(entry.numbers) + 1))
    return bool(entry.numbers) and entry.numbers not in (expected, [n + 1 for n in expected])


# ---- Yomitan rows ------------------------------------------------------------------------------------------------

def pos_tag(pos: str) -> str:
    """The abbreviation as Webster prints it (`v. t.`), without the spaces that would split it into two tags."""
    return pos.replace(" ", "") + "."


def sense_item(sense: Sense) -> dict:
    content: list = []
    if sense.field:
        content.append(sc("tags", [sc("tag", sense.field, "span")], "span"))
    content.append(" ".join([sense.text] + sense.more).strip())
    if sense.subs:
        content.append({"tag": "ul", "content": [{"tag": "li", "content": s} for s in sense.subs]})
    return {"tag": "li", "content": {"tag": "div", "content": content}}


def entry_content(entry: Entry) -> list:
    content: list = []
    toggles: list = []
    if entry.grammar:
        toggles.append({"tag": "details", "content": [sc("summary-entry", "Grammar", "summary"), sc("Grammar-content", entry.grammar)]})
    if entry.etymology:
        toggles.append({"tag": "details", "content": [sc("summary-entry", "Etymology", "summary"), sc("Etymology-content", entry.etymology)]})
    if toggles:
        content.append(sc("preamble", toggles))
    content.append(sc("glosses", [sense_item(s) for s in entry.senses if s.text or s.subs or s.more], "ol"))
    for label, text in entry.notes:
        parts = [{"tag": "span", "data": {"content": "bold-text"}, "content": f"{label}. "}] if label else []
        content.append(sc("extra-info", [*parts, text]))
    for text in entry.stray:
        content.append(sc("extra-info", text))
    content.append(sc("backlink", [
        "Webster's Revised Unabridged Dictionary (1913), public domain. ",
        {"tag": "a", "href": GUTENBERG_URL, "content": "Project Gutenberg"},
    ]))
    return content


def build(entries: list[Entry]) -> tuple[list[TermRow], list[Tag]]:
    rows: list[TermRow] = []
    tags: dict[str, Tag] = {}
    for entry in entries:
        if entry.failure:
            continue
        names: list[str] = []
        if entry.pos:
            name = pos_tag(entry.pos)
            tags.setdefault(name, Tag(name, "partOfSpeech", POS_NOTES.get(entry.pos, entry.pos), len(tags)))
            names.append(name)
        if entry.entry_field:
            name = "field:" + entry.entry_field
            tags.setdefault(name, Tag(name, "field", entry.entry_field, len(tags)))
            names.append(name)
        definitions = [{"type": "structured-content", "content": entry_content(entry)}]
        for variant in dict.fromkeys(v.strip().lower() for v in entry.headword.split(";")):
            rows.append(TermRow(
                term=variant, definition_tags=" ".join(names), score=0, definitions=definitions,
                sequence=len(rows) + 1,
            ))
    return rows, list(tags.values())


def report(entries: list[Entry]) -> str:
    failures = [e for e in entries if e.failure]
    clean = len(entries) - len(failures)
    irregular = [e for e in entries if not e.failure and numbering_irregular(e)]
    stray = [e for e in entries if not e.failure and e.stray]
    reasons = Counter(re.sub(r"'.*?'", "…", e.failure) for e in failures)
    out = [
        "Webster's 1913 parse report",
        f"headwords found:   {len(entries)}",
        f"parsed cleanly:    {clean} ({100 * clean / max(len(entries), 1):.2f}%)",
        f"failed (left out): {len(failures)}",
        f"warnings (kept):   {len(irregular)} with irregular sense numbering, {len(stray)} with paragraphs the parser did not recognise",
        "",
        "Failure reasons:",
        *[f"  {n:6d}  {r}" for r, n in reasons.most_common()],
        "",
        "Failures (source line, headword, reason):",
        *[f"  {e.line}\t{e.headword}\t{e.failure}" for e in failures],
        "",
        "Warning: irregular numbering (source line, headword, numbers):",
        *[f"  {e.line}\t{e.headword}\t{e.numbers}" for e in irregular],
        "",
        "Warning: unrecognised paragraphs kept as plain notes (source line, headword, first 80 characters):",
        *[f"  {e.line}\t{e.headword}\t{e.stray[0][:80]}" for e in stray],
        "",
    ]
    return "\n".join(out)


def convert(source_path: Path, out_dir: Path) -> tuple[Path, Path, int, str]:
    with source_path.open(encoding="utf-8", newline="") as f:
        text = f.read()
    entries, revision = parse(text)
    rows, tags = build(entries)
    meta = Meta(
        file_name=FILE_NAME,
        title="Webster's Revised Unabridged Dictionary (1913)",
        revision=f"{revision}.{CONVERTER_RELEASE}",
        author="alrisa (conversion); Noah Webster, G. & C. Merriam Co. (text)",
        attribution=(
            "Webster's Revised Unabridged Dictionary, 1913 edition, public domain, from Project Gutenberg ebook "
            "#29765 (https://www.gutenberg.org/ebooks/29765). Converted to Yomitan format by fumika-dictionaries."
        ),
        url=GUTENBERG_URL,
        description="English to English: a large historical dictionary (1913), public domain. Wording is dated.",
    )
    zip_path, index_path, count = write_dictionary(out_dir, meta, rows, tags)
    text_report = report(entries)
    report_path = out_dir / f"{FILE_NAME}-parse-report.txt"
    with report_path.open("w", encoding="utf-8", newline="") as f:
        f.write(text_report)
    return zip_path, index_path, count, text_report


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    zip_path, index_path, count, text_report = convert(Path(argv[1]), Path(argv[2]))
    print("\n".join(text_report.split("\n")[:12]))
    print(f"{count} entries -> {zip_path} ({zip_path.stat().st_size} bytes), {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
