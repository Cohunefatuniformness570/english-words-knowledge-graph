#!/usr/bin/env bash
set -euo pipefail

# Constants
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_ROOT/venv"
PYTHON="python3"
DATA_DIR="$REPO_ROOT/data"
WIKTIONARY_URL="https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2"
NGGRAM_BASE="https://storage.googleapis.com/books/ngrams/books/googlebooks-eng-all-1gram-20120701-"
NGGRAM_SHARDS=(a b c d e f g h i j k l m n o p q r s t u v w x y z)
ARTIFACT_CACHE="$REPO_ROOT/artifacts/cache.tar.gz"
ARTIFACT_META_DIR="$REPO_ROOT/artifacts/metadata"
SHARD_RECORD="$ARTIFACT_META_DIR/ngram_shards.txt"

log() {
  printf '[setup] %s\n' "$1"
}

ensure_python() {
  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    log "python3 not found; install Python 3 before running this script"
    exit 1
  fi
}

ensure_http_clients() {
  if command -v curl >/dev/null 2>&1; then
    HTTP_CLIENT="curl"
  elif command -v wget >/dev/null 2>&1; then
    HTTP_CLIENT="wget"
  else
    log "neither curl nor wget is available; install one to download datasets"
    exit 1
  fi
}

create_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    log "creating virtual environment"
    "$PYTHON" -m venv "$VENV_DIR"
  fi
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  log "upgrading pip"
  pip install --upgrade pip
}

install_requirements() {
  log "installing Python dependencies"
  pip install -r "$REPO_ROOT/requirements.txt"
}

ensure_dirs() {
  log "creating data and artifact directories"
  mkdir -p \
    "$REPO_ROOT/data/wiktionary" \
    "$REPO_ROOT/data/ngrams" \
    "$REPO_ROOT/artifacts/lemmas" \
    "$REPO_ROOT/artifacts/years" \
    "$REPO_ROOT/artifacts/trie" \
    "$REPO_ROOT/artifacts/layout" \
    "$REPO_ROOT/outputs/frames" \
    "$ARTIFACT_META_DIR"
}

restore_artifact_cache() {
  if [ -f "$ARTIFACT_CACHE" ]; then
    log "restoring cached artifacts"
    tar -xzf "$ARTIFACT_CACHE" -C "$REPO_ROOT"
  fi
}

checkpoint_artifacts() {
  if [ -d "$REPO_ROOT/artifacts" ]; then
    log "saving artifact cache"
    mkdir -p "$REPO_ROOT/artifacts"
    tar --exclude="$(basename "$ARTIFACT_CACHE")" -czf "$ARTIFACT_CACHE" -C "$REPO_ROOT" artifacts
  fi
}

download_wiktionary() {
  local target="$DATA_DIR/wiktionary/enwiktionary-latest-pages-articles.xml.bz2"
  if [ -f "$target" ]; then
    log "wiktionary dump already present"
    return
  fi
  log "downloading wiktionary dump"
  mkdir -p "$(dirname "$target")"
  if [ "$HTTP_CLIENT" = "curl" ]; then
    curl -L "$WIKTIONARY_URL" -o "$target"
  else
    wget -O "$target" "$WIKTIONARY_URL"
  fi
}

is_gzip() {
  local file="$1"
  "$PYTHON" -c 'import io, sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    with path.open("rb") as handle:
        head = handle.read(2)
    sys.exit(0 if head == b"\x1f\x8b" else 1)
except FileNotFoundError:
    sys.exit(1)
except OSError:
    sys.exit(1)' "$file"
}

download_ngrams() {
  mkdir -p "$DATA_DIR/ngrams"
  for legacy in "$DATA_DIR"/ngrams/eng-all-1gram-*.gz; do
    if [ -e "$legacy" ]; then
      log "removing legacy shard $(basename "$legacy")"
      rm -f "$legacy"
    fi
  done
  for shard in "${NGGRAM_SHARDS[@]}"; do
    local name="${NGGRAM_BASE##*/}${shard}.gz"
    local target="$DATA_DIR/ngrams/${name}"
    local url="${NGGRAM_BASE}${shard}.gz"
    if [ -f "$target" ]; then
      if is_gzip "$target"; then
        log "ngram shard ${name} already present"
        continue
      fi
      log "existing shard ${name} is invalid; re-downloading"
      rm -f "$target"
    fi
    log "downloading ngram shard ${name}"
    if [ "$HTTP_CLIENT" = "curl" ]; then
      curl -L "$url" -o "$target"
    else
      wget -O "$target" "$url"
    fi
    if ! is_gzip "$target"; then
      log "downloaded shard ${name} is not a valid gzip; please check the URL"
      exit 1
    fi
  done
}

run_pipelines() {
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  local expected_shards="${NGGRAM_SHARDS[*]}"
  local rebuild=0
  if [ ! -f "$REPO_ROOT/artifacts/trie/prefix_counts.jsonl" ]; then
    rebuild=1
  elif [ ! -f "$SHARD_RECORD" ]; then
    rebuild=1
  else
    local recorded
    recorded=$(<"$SHARD_RECORD")
    if [ "$recorded" != "$expected_shards" ]; then
      rebuild=1
    fi
  fi
  if [ "$rebuild" -eq 1 ]; then
    log "extracting lemmas from wiktionary"
    python -m src.ingest.wiktionary_extract "$DATA_DIR/wiktionary/enwiktionary-latest-pages-articles.xml.bz2" "$REPO_ROOT/artifacts/lemmas/lemmas.tsv"
    log "computing first-year data"
    python -m src.ingest.ngram_first_year "$REPO_ROOT/artifacts/lemmas/lemmas.tsv" "$DATA_DIR/ngrams" "$REPO_ROOT/artifacts/years/first_years.tsv"
    log "building prefix trie"
    python -m src.build.build_prefix_trie "$REPO_ROOT/artifacts/years/first_years.tsv" "$REPO_ROOT/artifacts/trie/prefix_counts.jsonl"
    printf '%s
' "$expected_shards" >"$SHARD_RECORD"
    checkpoint_artifacts
  else
    log "cached prefix counts match shard set; skipping ingest and build"
  fi
  log "rendering frames"
  python -m src.viz.render_frames "$REPO_ROOT/artifacts/trie/prefix_counts.jsonl" "$REPO_ROOT/outputs/frames"
  log "encoding video and gif"
  python -m src.viz.encode "$REPO_ROOT/outputs/frames" "$REPO_ROOT/outputs/english_trie_timelapse.mp4" "$REPO_ROOT/outputs/english_trie_timelapse.gif"
}

main() {
  ensure_python
  ensure_http_clients
  create_venv
  install_requirements
  ensure_dirs
  restore_artifact_cache
  download_wiktionary
  download_ngrams
  run_pipelines
  log "setup complete. activate with 'source venv/bin/activate'"
}

main "$@"
