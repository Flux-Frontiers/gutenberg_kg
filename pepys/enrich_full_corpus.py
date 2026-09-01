"""Enrich the full Pepys corpus with topic classification.

Loads all pre-chunked entries from pepys_clean_chunks.pkl, runs Phase 3
(hybrid topic classification) on each chunk, and writes the enriched output
to pepys_enriched_full.txt for use in embedding experiments.

Usage:
    poetry run python pepys/enrich_full_corpus.py
    poetry run python pepys/enrich_full_corpus.py --output pepys/my_output.txt
    poetry run python pepys/enrich_full_corpus.py --max-chunks 3 --seed 42
"""

import argparse
import pickle
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from personal_agent.tools.diary_transformer import DiaryEntry, DiaryTransformer, EntryChunk


def enrich_corpus(
    pkl_path: str,
    output_path: str,
    max_chunks_per_entry: int = 3,
    seed: int = 42,
) -> None:
    """Load pre-chunked entries from pkl, classify topics, save enriched output.

    :param pkl_path: Path to pepys_clean_chunks.pkl
    :param output_path: Path to write enriched pipe-delimited output
    :param max_chunks_per_entry: Cap on chunks per entry (matches transformer default)
    :param seed: Random seed for reproducible k-means fallback
    """
    print(f"Loading chunk cache: {pkl_path}")
    with open(pkl_path, "rb") as f:
        cache = pickle.load(f)

    raw_entries = cache["entries"]
    print(f"Loaded {len(raw_entries)} entries (version {cache['version']})")

    # Reconstruct DiaryEntry objects from pkl dicts
    entries: list[DiaryEntry] = []
    for e in raw_entries:
        entries.append(
            DiaryEntry(
                timestamp=datetime.fromisoformat(e["timestamp"]),
                original_type=e["original_type"],
                category=e["category"],
                content=e["content"],
                index=e["index"],
                chunks=e["chunks"][:max_chunks_per_entry] if e["chunks"] else [],
            )
        )

    # Collect all chunk texts for unsupervised category discovery
    all_chunk_texts = []
    for entry in entries:
        if entry.chunks:
            all_chunk_texts.extend(entry.chunks)
    print(f"Total chunks to classify: {len(all_chunk_texts)}")

    # Initialise transformer (loads spaCy + sentence-transformers)
    print("Initialising DiaryTransformer...")
    transformer = DiaryTransformer()

    # Discover semantic categories for k-means fallback (unsupervised)
    print("Discovering semantic categories...")
    categories = transformer.discover_semantic_categories(all_chunk_texts, seed=seed)

    # Classify each chunk and build EntryChunk list
    print("Classifying chunks...")
    memory_chunks: list[EntryChunk] = []
    total = len(all_chunk_texts)
    chunk_counter = 0

    for entry_idx, entry in enumerate(entries):
        if not entry.chunks:
            continue
        for chunk_text in entry.chunks:
            if chunk_counter > 0 and chunk_counter % 500 == 0:
                pct = chunk_counter * 100 // total
                print(f"  {chunk_counter}/{total} chunks ({pct}%)")
            chunk_counter += 1

            semantic_category, _ = transformer.classify_chunk_hybrid(chunk_text, categories)
            context = transformer.extract_context(chunk_text)

            chunk = EntryChunk(
                timestamp=entry.timestamp,
                semantic_category=semantic_category,
                context_classification=context,
                content=chunk_text,
                confidence=1.0,
                phase="immediate",
            )
            chunk.source_entry_index = entry_idx
            chunk.source_entry = entry
            memory_chunks.append(chunk)

    print(f"Classified {len(memory_chunks)} chunks across {len(entries)} entries")

    # Sort chronologically
    memory_chunks.sort(key=lambda m: m.timestamp)

    # Save enriched output
    run_params = {
        "timestamp": datetime.now().isoformat(),
        "input_file": pkl_path,
        "batch_size": len(entries),
        "chunk_size": transformer.max_chunk_length,
        "max_chunks_per_entry": max_chunks_per_entry,
        "seed": seed,
    }
    transformer.save_entries(memory_chunks, output_path, run_params)
    print(f"\nDone. {len(memory_chunks)} enriched chunks written to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    pepys_dir = Path(__file__).parent
    parser.add_argument(
        "--pkl",
        default=str(pepys_dir / "pepys_clean_chunks.pkl"),
        help="Path to pepys_clean_chunks.pkl (default: pepys/pepys_clean_chunks.pkl)",
    )
    parser.add_argument(
        "--output",
        default=str(pepys_dir / "pepys_enriched_full.txt"),
        help="Output path (default: pepys/pepys_enriched_full.txt)",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=3,
        help="Max chunks per entry (default: 3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for k-means (default: 42)",
    )
    args = parser.parse_args()

    enrich_corpus(
        pkl_path=args.pkl,
        output_path=args.output,
        max_chunks_per_entry=args.max_chunks,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
