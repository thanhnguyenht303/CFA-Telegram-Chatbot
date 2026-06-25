from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cfa_vocab_bot.__main__ import _import_timeline

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/import_timeline.py data/sample_timeline.csv [user_id]")
    user_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    _import_timeline(sys.argv[1], user_id)

