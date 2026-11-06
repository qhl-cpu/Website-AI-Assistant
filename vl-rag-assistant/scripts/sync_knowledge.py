"""Run knowledge ingestion in order, stopping before stale data can be uploaded."""

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_MODULES = {
    "requests": "requests",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "openai": "openai",
    "qdrant_client": "qdrant-client",
    "tiktoken": "tiktoken",
}


def check_dependencies() -> None:
    missing = [
        package
        for module, package in REQUIRED_MODULES.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        raise RuntimeError(
            f"Missing dependencies in {sys.executable}: {', '.join(missing)}.\n"
            f'Install them with: "{sys.executable}" -m pip install '
            f'-r "{PROJECT_ROOT / "requirements.txt"}"'
        )


def fingerprint(path: Path) -> tuple[int, int, int] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


def run_pipeline(project_root: Path, *, upload: bool = False) -> None:
    steps = [
        ("01_ingest_wordpress.py", "data/raw/wp_documents_raw.jsonl"),
        ("02_clean_documents.py", "data/processed/wp_documents_clean.jsonl"),
        ("03_chunk_documents.py", "data/processed/wp_chunks.jsonl"),
        ("04_embed_chunks.py", "data/processed/wp_chunks_embedded.jsonl"),
    ]
    for script_name, output_name in steps:
        output = project_root / output_name
        before = fingerprint(output)
        print(f"\nRunning {script_name}", flush=True)
        subprocess.run(
            [sys.executable, str(project_root / "scripts" / script_name)],
            cwd=project_root,
            check=True,
        )
        after = fingerprint(output)
        if after is None or after == before or output.stat().st_size == 0:
            raise RuntimeError(
                f"{script_name} did not produce a fresh, nonempty {output_name}. "
                "Stopping instead of using an old or empty file."
            )

    if upload:
        print("\nUploading the freshly generated embeddings to Qdrant.", flush=True)
        subprocess.run(
            [
                sys.executable,
                str(project_root / "backend/scripts/upload_chunks_to_qdrant.py"),
            ],
            cwd=project_root / "backend",
            check=True,
        )
    else:
        print("\nFresh embeddings prepared locally. Qdrant upload was not requested.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch WordPress content, clean it, split it, and generate fresh "
            "embeddings using the configured OpenAI API (billed usage). "
            "Each step must succeed before the next starts."
        )
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Also write the fresh embeddings to the configured Qdrant collection.",
    )
    args = parser.parse_args()
    try:
        check_dependencies()
        run_pipeline(PROJECT_ROOT, upload=args.upload)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nKnowledge sync stopped: {error}", file=sys.stderr)
        print("No later pipeline steps were run.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
