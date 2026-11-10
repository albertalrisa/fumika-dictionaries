<img src="assets/fumika.png" alt="Fumika" width="128" height="128">

# fumika-dictionaries

Starter dictionaries for the [Fumika](https://fumika.alrisa.jp/) EPUB reader, converted to the Yomitan format
(format 3, structured content). Each folder holds one dictionary's converter, tests, source licence and README.

| Folder | Dictionary | Source licence |
|---|---|---|
| `wordnet/` | Open English WordNet (2025) | CC BY 4.0 |
| `webster/` | Webster's Revised Unabridged Dictionary (1913) | Public domain (Project Gutenberg #29765) |

Entries use the structured-content names Fumika already lays out for the Wiktionary dictionaries (`glosses`,
`details-entry-examples`, `related-words`, `backlink`, ...), so its Define view needs no extra code.
`fumika_dict_common/` holds the writer both converters share.

## Rebuild

Python 3.10 or newer, standard library only. Downloads go to `sources/<dictionary>/` (gitignored), one empty folder
per download, and are treated as untrusted data: the converters run with `-I`.

```
python -I wordnet/convert.py sources/wordnet/english-wordnet-2025.xml.gz dist
python -I webster/convert.py sources/webster/pg29765.txt dist
```

Each run writes `dist/<name>.zip` and `dist/<name>.json` (the index, for update checks). Releases attach both under
the names the index's `downloadUrl` and `indexUrl` point at
(`https://github.com/albertalrisa/fumika-dictionaries/releases/latest/download/<name>.zip` and `<name>.json`).

## Test

```
python -I -m unittest discover -s fumika_dict_common -t .
python -I -m unittest discover -s wordnet -t .
python -I -m unittest discover -s webster -t .
```

The tests that compare against the real sources are skipped when `sources/` is empty.
