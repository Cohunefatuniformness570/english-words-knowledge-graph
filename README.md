# English Lexicon Time Machine

> Watch the entire English language blossom from Wiktionary + Google Books N-grams, rendered as a living, breathing prefix galaxy.

## How this repo is put together

- **Zero-config takeover** – `./setup.sh` spins up the virtualenv, fetches every dataset, caches the heavy lifts, and ships final MP4/GIF output.
- **Radial growth cinematics** – the trie erupts from the core alphabet, framing decades of linguistic evolution as a neon fractal.
- **Repeatable science** – every artifact (lemmata, first-year inference, trie counts, layouts) checkpoints to disk and into a reusable tarball for instant re-renders.
- **Battle-tested** – streams 26 full 1-gram shards, handles 1.4GB Wiktionary dumps, and renders 220 frames in glorious 1080p.

Share it, remix it, drop it in your next data-viz thread.

## Quickstart

```bash
cd /Users/grey/Projects/graph-visualizations
bash setup.sh
```

The script will:

1. Create/upgrade `venv/` with Python 3.
2. Download Wiktionary + Google Books 1-gram shards (`a`–`z`).
3. Extract English lemmas, infer first-use years, aggregate prefix counts.
4. Render 220 radial frames (`outputs/frames/frame-0000.png` → `frame-0219.png`).
5. Encode `outputs/english_trie_timelapse.mp4` and a share-ready GIF.

Rerun the script anytime—artifact caching means future passes jump straight to rendering.

## Anatomy

| Stage | Script | Output |
|-------|--------|--------|
| Lemma extraction | `src/ingest/wiktionary_extract.py` | `artifacts/lemmas/lemmas.tsv` |
| First-year inference | `src/ingest/ngram_first_year.py` | `artifacts/years/first_years.tsv` |
| Prefix aggregation | `src/build/build_prefix_trie.py` | `artifacts/trie/prefix_counts.jsonl` |
| Layout generation | `src/viz/layout.py` | `artifacts/layout/prefix_positions.json` (legacy back-compat) |
| Frame rendering | `src/viz/render_frames.py` | `outputs/frames/` |
| Encoding | `src/viz/encode.py` | `outputs/english_trie_timelapse.mp4` + `.gif` |

## Render Only (after initial run)

```bash
source venv/bin/activate
python -m src.viz.render_frames artifacts/trie/prefix_counts.jsonl outputs/frames
python -m src.viz.encode outputs/frames outputs/english_trie_timelapse.mp4 outputs/english_trie_timelapse.gif
```

Use flags such as `--min-radius`, `--max-radius`, `--base-edge-alpha`, or `--start-progress` to tune the vibe.

## Neo4j Playground (Optional)

Load `artifacts/years/first_years.tsv` to explore in Neo4j (Community & Enterprise safe):

```cypher
:param batch => $rows;
UNWIND $rows AS row
WITH row WHERE row.word IS NOT NULL AND row.word <> ""
MERGE (w:Word {text: row.word})
SET w.first_year = CASE
  WHEN row.first_year = "" THEN NULL
  ELSE toInteger(row.first_year)
END;
```

## Share-Worthy Ideas

- Drop the GIF in language history threads (#linguistics #dataart).
- Remix the radial layout with alternative color ramps or depth cutoffs.
- Pair the timelapse with poetry readings for maximum feels.

## Credits

- Wiktionary community & Google Books N-gram team for open data.
- You, for showing the world how beautifully language grows.

## Community

For more open source software and content on Knowledge Graphs, GNNs, and Graph Databases, [Join our community on X!](https://x.com/i/communities/1977449294861881612)
