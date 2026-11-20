"""Run the shared knowledge pipeline stage from the command line."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.knowledge.wordpress import main


if __name__ == "__main__":
    main()
