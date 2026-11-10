# Webster's Revised Unabridged Dictionary (1913)

- **Source:** Project Gutenberg ebook #29765, "Webster's Unabridged Dictionary", plain text (UTF-8), from
  https://www.gutenberg.org/ebooks/29765.txt.utf-8 (the revision is the ebook's "Most recently updated" date).
- **Licence:** the text is in the public domain. `LICENSE-WEBSTER.txt` says so and carries the Project Gutenberg
  licence that ships with the ebook.
- **Output:** `webster1913.zip`, `webster1913.json` and `webster1913-parse-report.txt`.

## How entries are read

The text is irregular, so the converter is strict and measures itself. An entry is a headword line (capitals, after a
blank line) up to the next one. It parses cleanly when

1. the headline after it (`Bate"ment, n. Etym: [...]`) names that headword (syllable marks removed, ligatures folded,
   `;`-separated variants allowed), and
2. its body gives at least one sense with text: a numbered sense (with `(a)` sub-senses and a `(Field)` label), or a
   `Defn:` paragraph.

Entries that fail are **left out** and listed in the report with their source line and reason; nothing is repaired by
guesswork. Paragraphs the parser does not recognise stay in the entry as plain notes and are listed as warnings.
`Note:`, `Syn.` and `--` lines are kept as notes under the senses. Quotations stay inside the sense text: the source
does not mark them reliably.

Terms are lower case (Fumika looks lower-cased words up); an entry with variants (`COWRIE; COWRY`) gets one row per
variant. Source line numbers in the report are line numbers of the Gutenberg file.

The committed `PARSE-REPORT.txt` is the report of the last release build.

## Layout of an entry

`preamble` (Grammar and Etymology toggles) > `glosses` (numbered senses, field labels as tags, sub-senses as a list) >
`extra-info` notes > `backlink` to the ebook.

## Rebuild

```
mkdir -p sources/webster
curl -L -o sources/webster/pg29765.txt https://www.gutenberg.org/ebooks/29765.txt.utf-8
python -I webster/convert.py sources/webster/pg29765.txt dist
python -I -m unittest discover -s webster -t .
```
