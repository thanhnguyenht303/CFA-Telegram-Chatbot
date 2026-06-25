from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cfa_vocab_bot.__main__ import _init_db

if __name__ == "__main__":
    _init_db()

