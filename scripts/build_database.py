"""Kept for backwards compatibility: the pipeline now lives in pipeline/.

    python scripts/build_database.py      ==      python -m pipeline.build
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.build import main  # noqa: E402

if __name__ == "__main__":
    main()
