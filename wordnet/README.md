# Open English WordNet

- **Source:** Open English WordNet 2025 edition, WN-LMF XML, from
  https://github.com/globalwordnet/english-wordnet/releases/tag/2025-edition
  (`english-wordnet-2025.xml.gz`, the base edition, not "plus").
- **Licence:** CC BY 4.0, full text in `LICENSE-OEWN.txt`. Every entry carries the attribution line and a link to
  en-word.net; the index's `attribution` names the source and licence.
- **Output:** `oewn.zip` and `oewn.json`.

## Layout of an entry

One term row per headword and part of speech (tags `n`, `v`, `adj`, `adv`; adjective satellites count as adjectives).
Its structured content holds:

- `glosses`: a numbered list, one item per synset in the source's sense order (the order WordNet lists a word's
  senses); each item is the definition, with its examples folded into `details-entry-examples`;
- `related-words` > `synonyms`: the other lemmas of the word's synsets (all senses together, first 30), as lookup
  links;
- `backlink`: the attribution and a link to the word on en-word.net.

## Rebuild

```
mkdir -p sources/wordnet
curl -L -o sources/wordnet/english-wordnet-2025.xml.gz \
  https://github.com/globalwordnet/english-wordnet/releases/download/2025-edition/english-wordnet-2025.xml.gz
python -I wordnet/convert.py sources/wordnet/english-wordnet-2025.xml.gz dist
python -I -m unittest discover -s wordnet -t .
```
